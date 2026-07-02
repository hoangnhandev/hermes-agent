# Phase C — Deploy Correctness (wires 6a, 6b, 6c)

## Context Links
- Plan: [`plan.md`](plan.md) | Brainstorm: `plans/reports/brainstormer-260702-0927-google-ads-flow-completion.md`
- Độc lập (chạy song song A/B được) | Files: `scripts/deploy.py`, `scripts/creator.py`, `scripts/_budget_calc.py`, `scripts/monitor.py`, `scripts/daily_report.py`, `google-ads.env`, `google-ads.env.example`

## Overview
- **Priority:** P2 (correctness + money-safety) | **Status:** complete | **Effort:** ~4.5h
- Sửa đúng deploy: negatives thực sự apply; MONTHLY_BUDGET env sane; date account-local.

## Key Insights
- **Negatives:** `research.py` emit `keyword_seeds.negative` ("vf3 cũ", "review vf3"…)
  nhưng `deploy.py` chỉ tạo positive keywords (`create_keywords:174`). Trên budget nhỏ,
  click lãng phí vào intent "xe cũ/tin tức" càng đau.
- **MONTHLY_BUDGET stale:** memory `hermes-google-ads-setup` ghi env thật có
  `MONTHLY_BUDGET=500` (USD placeholder cũ). Code giờ VND-native → hiểu **500 VND/mo**
  = cap vỡ (block mọi campaign). **Money-safety gotcha.** `env.example` default `6000000`
  mâu thuẫn ví dụ doc `--budget 10000000`.
- **Date:** GAQL `segments.date` đã account-local (VN=UTC+7); vấn đề là `detected_at`/reporting
  day dùng `datetime('now')`=UTC → lệch biên ngày.

## Requirements
- **Func:** deploy apply negatives (campaign-level); MONTHLY_BUDGET env sane + validation;
  date nhất quán account-local.
- **Non-func:** negatives = thêm criteria (không tăng spend); validation warn không block.

## Architecture / Data Flow
```
deploy.py ──sau create_keywords──► create_negative_keywords(plan.keyword_seeds.negative)  [6a]
google-ads.env ──verify──► MONTHLY_BUDGET=5000000 + ACCOUNT_CURRENCY=VND                  [6b]
monitor/daily_report ──account-local date──► consistent day boundary                      [6c]
```

## Related Code Files
- **Modify:** `scripts/deploy.py` (thêm `create_negative_keywords`), `scripts/creator.py`
  (validation warn MONTHLY_BUDGET <1M), `scripts/monitor.py` + `scripts/daily_report.py`
  (date consistency), `google-ads.env` (verify/sửa — gitignored), `google-ads.env.example`.
- **Read-only:** `scripts/_budget_calc.py` (account_currency), `scripts/research.py` (negative seeds).

## Implementation Steps
**Wire 6a — Negatives deploy:**
1. `deploy.py`: thêm `create_negative_keywords(client, customer_id, campaign_resource_name, negatives: List[str])`.
   Dùng `CampaignCriterion` với `negative_keyword` (campaign-level, đơn giản nhất — KISS).
2. `deploy_full_campaign`: sau `create_keywords`, gọi `create_negative_keywords` với
   `plan['keyword_seeds']['negative']` (adapter `_research_to_deploy_plan` phải pass negatives).
3. Update `_research_to_deploy_plan` (`creator.py`): thêm `"negatives": seeds.get("negative", [])`.
4. Mock path: trả list resource names giả (như create_keywords mock).

**Wire 6b — MONTHLY_BUDGET:**
5. Verify/sửa `google-ads.env` THẬT (gitignored): `MONTHLY_BUDGET=5000000`, `ACCOUNT_CURRENCY=VND`.
   (Không commit file thật.)
6. `google-ads.env.example`: comment rõ default nên = ngân sách thật (VD `5000000`), khớp phase.
7. `creator.py` + `_budget_calc.py`: validation — warn (KHÔNG block) nếu `MONTHLY_BUDGET < 1_000_000`
   (dưới sàn → khả năng cấu hình sai VND/USD). In warning rõ.

**Wire 6c — UTC→account-local date:**
8. Xác định account `time_zone` (query `customer.time_zone` 1 lần, cache; hoặc env `ACCOUNT_TZ` default `Asia/Ho_Chi_Minh`).
9. `monitor.py`: `detected_at`/sync date dùng account-local (chuyển UTC→local khi ghi/log).
10. `daily_report.py`: reporting "yesterday" = account-local yesterday (không UTC).
11. Doc: ghi rõ segments.date đã account-local trong SKILL.md (update Known Limitations).

## Todo List
- [ ] 6a: deploy.create_negative_keywords (CampaignCriterion)
- [ ] 6a: adapter _research_to_deploy_plan pass negatives
- [ ] 6a: mock path
- [ ] 6b: verify/sửa google-ads.env thật (500→5000000)
- [ ] 6b: env.example default rõ
- [ ] 6b: validation warn MONTHLY_BUDGET <1M
- [ ] 6c: account time_zone (query/env)
- [ ] 6c: monitor detected_at account-local
- [ ] 6c: daily_report yesterday account-local
- [ ] 6c: SKILL.md Known Limitations update
- [ ] Verify: mock deploy có negatives + env sanity

## Success Criteria
- `creator.py --approve <uuid> --indices 1,3 --mock` → log `[NEGATIVES] Created N negative keywords` + list.
- `echo $MONTHLY_BUDGET` từ env thật ≥ 1_000_000; `ACCOUNT_CURRENCY=VND`.
- Validation warn in ra khi MONTHLY_BUDGET thấp.
- Daily report day boundary khớp account-local (spot-check giờ VN).

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| Negatives campaign-level quá rộng (chặn term cần thiết) | Low | Review negative list trước deploy; dễ gỡ |
| Env thật chưa sửa → cap vỡ | Med | Verify đầu phase; checklist go-live |
| time_zone query thêm 1 API call | Low | Cache; fallback env Asia/Ho_Chi_Minh |

## Security Considerations
- Negatives = chặn query (giảm spend lãng phí), không tăng spend.
- Không commit `google-ads.env` thật (gitignored, chứa refresh token).

## Next Steps
- Sau A+B+C: skill skeleton khép. Go-live còn chờ Basic Access (Google review).
- Update SKILL.md Known Limitations (gỡ mục đã fix: negatives, anomaly→Telegram, date).
