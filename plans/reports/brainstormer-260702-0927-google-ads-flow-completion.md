# Brainstorm — Hoàn thiện skeleton flow google-ads

**Date:** 2026-07-02 | **Status:** Approved (full scope incl. wire 5) | **Next:** `/ck:plan`

## Problem statement
Skill google-ads có nửa flow (research→duyệt→deploy) production-grade, nhưng nửa (monitor→report→optimize) **scaffolded chưa chạy**. Skeleton đã dự liệu sẵn nhiều thứ (schema, read-path) nhưng thiếu "nối dây cuối" → vòng closed-loop không khép. Mục tiêu: **hoàn thiện khung sườn hoạt động** (chiến thuật campaign tinh chỉnh sau). Verify trên **Test mode** (Dev Token có, chưa Basic Access). Conversion data **sẵn sàng** (mua-vinfast label + redeploy xong).

## Input xác nhận (từ user)
- Go-live: **Test mode** (verify test account, không live spend).
- Conversion data: **đã có label + redeploy** → conversion sẽ chảy khi monitor sync.
- Scope: **đầy đủ** P0+P1+P2 kể cả dashboard anomalies (wire 5).

## Tìm mấu chốt (scout)
Skeleton **đã có phần lớn** — chỉ thiếu dây nối:
- `daily_metrics` schema + `daily_report.get_top_keywords` đã support `entity_type='keyword'` → chỉ thiếu monitor **ghi**.
- `optimization_log` đã tạo + INSERT (optimize.py:206) → chỉ cần action cụ thể.
- `anomaly_log` + cờ `alert_sent` đã có → chỉ thiếu gọi Telegram sau `save_anomaly`.
- `has_conversion_tracking`: schema có (DEFAULT 0), **không ai set=1**, reconcile reset=0.
- Memory `hermes-google-ads-setup` **đã stale**: VND gap memory ghi "cần fix" thực ra **đã fix** (code VND-native). Nhưng env thật khả năng còn `MONTHLY_BUDGET=500` (USD placeholder cũ) → giờ code hiểu 500 VND/mo = vỡ money-safety.

## 8 wires (approach + alt bỏ vì)

| # | Wire | Fix ở đâu | Approach | Alt (bỏ) |
|---|---|---|---|---|
| 1 | Conversion flag wiring | `_store.save_campaign`, `monitor.reconcile_campaigns`, `creator.cmd_approve` | Derive từ env: `=1` nếu `GOOGLE_ADS_CONVERSION_ACTION_ID` có giá trị; reconcile giữ nguyên (COALESCE) thay reset | Probe API → thêm call+latency |
| 2 | Keyword metrics | `monitor.py` sync thêm GAQL `keyword_view` → `upsert_metric(entity_type='keyword')` | Query keyword_view, map text→keyword id, upsert. Schema+read sẵn | `--keyword-sync` mode riêng |
| 3 | optimize action cụ thể | `optimize.py` | Mỗi rec → action apply-able (`PAUSE kw`, `ADD negative`, `SCALE budget`), status `recommended`, log đã có. **Recommend-only** | Auto-apply → nguy cơ tắt sớm |
| 4 | Anomaly→Telegram | `monitor.py` sau `save_anomaly` + `telegram_notify.send_anomaly` | Ping report channel, set `alert_sent=1` (dedupe). Skip <7 ngày đã có | Severity routing |
| 5 | Dashboard anomalies | Workers `/api/sync` + `sync_to_d1.py` + dashboard panel | Thêm table `anomalies` D1, mở rộng payload, thêm panel | — |
| 6a | Negatives deploy | `deploy.py` | Tạo negative keyword criterion (campaign-level) từ `keyword_seeds.negative` | Shared negative list |
| 6b | MONTHLY_BUDGET stale | `google-ads.env` + `env.example` | Verify/sửa env thật `500→5000000`; validation warn nếu `<1_000_000` | — |
| 6c | UTC date | `monitor.py`/`daily_report.py` | `segments.date` đã account-local; chuẩn hóa `detected_at`/reporting nhất quán + doc | — |

## Sequencing (3 phase)
- **Phase A (P0):** wire 1+2 → monitor thu đủ data (conversion thật + keyword). Verify `monitor --mode sync` test account.
- **Phase B (P1):** wire 3+4+5 → optimize ra action + log; anomaly ping Telegram + dashboard. Verify optimize + synthetic anomaly.
- **Phase C (P2):** wire 6a+6b+6c → deploy đúng + money-safety env. Verify mock deploy có negatives + env sanity.

## Risks
| Risk | Sev | Mitigation |
|---|---|---|
| Map keyword API ↔ bảng `keywords` (criterion_id vs text) | Med | Xác định PK ở plan; fallback match by text |
| Test data mỏng → không trigger 30-conv/smart-bidding | Med | Verify phần khả thi; CPA-threshold verify sau Basic Access |
| Wire 5 chạm Workers → scope creep | Med | Tách module; Telegram (wire 4) đã đủ skeleton |
| Conversion flag từ env nhưng action chưa cháy → CPA rule trên số 0 | Low | User confirm đã redeploy; thêm guard skip CPA nếu conversions==0 |
| **Không path mới chi tiền** (read/sync/notify + negatives=thêm criteria + recommend-only) | ✅ Low | Money-safety giữ |

## Success metrics / validation
- Phase A: `daily_metrics` có row `entity_type='keyword'`; campaign `has_conversion_tracking=1`; conversions>0 (nếu test conversion fire).
- Phase B: `optimize.py` console + `optimization_log` có action cụ thể; anomaly ping Telegram; dashboard hiển thị anomalies.
- Phase C: `creator --approve --mock` log có negatives; `MONTHLY_BUDGET` env sanity (≥1M).

## Next steps / dependencies
- Dependency ngoài: Dev Token Test mode (đã có); Basic Access = verify live sau.
- Dependency mua-vinfast: label+redeploy (đã xong).
- Bắt đầu: `/ck:plan` chia 3 phase A/B/C theo 8 wires.

## Unresolved questions
- PK bảng `keywords` (criterion_id hay text) cho wire 2 matching — resolve ở plan phase.
- Wire 5: dashboard anomalies nằm ở infra nào chính xác (`plans/260629-1125-hermes-ads-copilot/infrastructure`?) — confirm ở plan.
