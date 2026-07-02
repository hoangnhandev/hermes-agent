# Phase A — Monitor Data Pipeline (wires 1, 2)

## Context Links
- Plan: [`plan.md`](plan.md) | Brainstorm: `plans/reports/brainstormer-260702-0927-google-ads-flow-completion.md`
- Files: `scripts/_store.py`, `scripts/monitor.py`, `scripts/creator.py`, `scripts/deploy.py`

## Overview
- **Priority:** P0 (nền tảng) | **Status:** complete | **Effort:** ~4h
- Làm monitor thu ĐỦ data thật: conversion flag + keyword-level metrics. Không có
  2 wires này → toàn bộ CPA/CTR/pacing anomaly + optimize keyword-level **chết**.

## Key Insights
- `has_conversion_tracking`: schema có (`_store.py:59` DEFAULT 0), reconcile query
  (`monitor.py:309`), nhưng **không ai set=1** + reconcile reset=0 mỗi sync.
- `daily_metrics` schema + `daily_report.get_top_keywords` (`daily_report.py:73`) **đã
  support** `entity_type='keyword'` — chỉ thiếu monitor **ghi** (hiện chỉ ghi campaign, `monitor.py:324`).
- Bảng `keywords` (`_store.py:85`): `id`, `campaign_id`, `keyword` (text), `match_type` —
  **không có criterion_id**. Deploy tạo 1 ad group/campaign → **text-match trong campaign đủ** (KISS).

## Requirements
- **Func:** monitor sync ghi metrics cho cả campaign + keyword; flag conversion tracking
  tự động =1 khi env có `GOOGLE_ADS_CONVERSION_ACTION_ID`.
- **Non-func:** không phá sync hiện tại; idempotent (UNIQUE entity_type+entity_id+date đã có).

## Architecture / Data Flow
```
Google Ads API ──GAQL campaign_report──► upsert_metric(entity_type='campaign')   [existing]
             ╲──GAQL keyword_view────► upsert_metric(entity_type='keyword')      [NEW wire 2]
env CONVERSION_ACTION_ID ──► has_conversion_tracking=1 tại save + reconcile giữ   [NEW wire 1]
```

## Related Code Files
- **Modify:** `scripts/_store.py` (`save_campaign`: set flag from env), `scripts/monitor.py`
  (`reconcile_campaigns`: preserve flag; sync: thêm keyword GAQL query + upsert loop),
  `scripts/creator.py` (`cmd_approve`: save_campaign thừa kế flag).
- **Read-only:** `scripts/deploy.py` (xác nhận 1 ad group/campaign), `scripts/daily_report.py`
  (get_top_keywords join đã sẵn).

## Implementation Steps
**Wire 1 — Conversion flag:**
1. `_store.save_campaign`: thêm `has_conversion_tracking = 1 if os.getenv("GOOGLE_ADS_CONVERSION_ACTION_ID","").strip() else 0` (đọc env).
2. `monitor.reconcile_campaigns`: thay `UPDATE ... has_conversion_tracking=0` → derive từ env (COALESCE/giữ); KHÔNG reset.
3. `creator.cmd_approve` path `save_campaign`: thừa kế logic (đã gọi save_campaign → tự động).
4. Guard: anomaly CPA rule skip nếu `conversions==0` (tránh false positive khi tracking chưa cháy).

**Wire 2 — Keyword metrics:**
5. `monitor.py` sync: thêm GAQL query:
   ```sql
   SELECT segments.date, campaign.id, ad_group.id,
          ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
          metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions,
          metrics.conversions_value
   FROM keyword_view
   WHERE segments.date >= '{range}' AND campaign.status = 'ENABLED'
     AND ad_group_criterion.status = 'ENABLED'
   ```
6. Map row → local: tìm `keywords.id` WHERE `campaign_id=? AND keyword=? (text) AND match_type=?`.
   Fallback: nếu không khớp (keyword mới do LLM thêm), insert row keywords mới (campaign_id từ API).
7. `upsert_metric(conn, 'keyword', <keywords.id>, date, impressions, clicks, cost_vnd, conv, conv_value)`.
   Cost: `from_micros(cost_micros)` (VND-native đã có).
8. Reuse retry/backoff + batch như campaign query.

## Todo List
- [ ] Wire 1: save_campaign set flag from env
- [ ] Wire 1: reconcile preserve flag (không reset)
- [ ] Wire 1: CPA anomaly guard skip conv==0
- [ ] Wire 2: GAQL keyword_view query trong sync
- [ ] Wire 2: map text→keywords.id + fallback insert
- [ ] Wire 2: upsert_metric entity_type='keyword'
- [ ] Verify: monitor --mode sync (test account)

## Success Criteria
- `monitor --mode sync` chạy không lỗi trên test account.
- `SELECT DISTINCT entity_type FROM daily_metrics` → có cả `'campaign'` và `'keyword'`.
- `SELECT has_conversion_tracking FROM campaigns WHERE status='active'` → `1` (với env có CONVERSION_ACTION_ID).
- Re-run sync → không duplicate (UNIQUE constraint).

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| Text-match sai nếu multi-ad-group sau | Low | Ghi chú TODO; thêm criterion_id khi cần |
| Keyword mới (LLM-added) không có trong bảng | Low | Fallback insert keywords row |
| GAQL keyword_view cần `segments.date` + permission | Med | Verify test account; fallback skip nếu API reject |

## Security Considerations
- Read-only API query (không mutate). Không thay đổi spend.
- Env đọc cho flag — không log secret.

## Next Steps
- Phase B phụ thuộc A (optimize cần keyword metrics + conversion data).
- C độc lập — chạy song song nếu đủ tay.
