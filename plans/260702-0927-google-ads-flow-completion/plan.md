---
title: "Hoàn thiện skeleton end-to-end flow google-ads"
description: "Nối 8 wires còn thiếu để khép vòng monitor→report→optimize. Skeleton đã có sẵn schema/read-path, chỉ thiếu dây nối. Verify Test mode. Không path mới chi tiền."
status: complete
priority: P1
effort: ~16h
branch: main
approach: wire-existing-skeleton
execution: sequential-phases-A-B-C
tags: [google-ads, hermes-skill, monitor, optimize, closed-loop, cloudflare-d1, money-safety]
created: 2026-07-02
blockedBy: []
blocks: []
related: [260630-0020-google-ads-skill-fix, 260629-1125-hermes-ads-copilot]
---

# Hoàn thiện skeleton flow google-ads — Implementation Plan

## Overview
Skill google-ads: nửa flow (research→duyệt→deploy) đã production-grade, nửa
(monitor→report→optimize) scaffolded **chưa chạy**. Skeleton đã dự liệu sẵn
nhiều thứ (schema `daily_metrics.entity_type`, `daily_report.get_top_keywords`,
`optimization_log`, `anomaly_log.alert_sent`) — chỉ thiếu "nối dây cuối".

Mục tiêu: **khép vòng closed-loop** (chiến thuật campaign tinh chỉnh sau).
Verify trên **Test mode** (Dev Token có, chưa Basic Access). Conversion data
sẵn sàng (mua-vinfast label + redeploy xong).

**Brainstorm:** `plans/reports/brainstormer-260702-0927-google-ads-flow-completion.md`

## Cross-plan relationship
- `260630-0020-google-ads-skill-fix` (P1, 9 phase): **đã thực thi phần lớn**
  (commits `phases 03/06/07/08/09` + VND fix). `status: pending` stale. Plan
  này = continuation, phủ phần loop-closure skill-fix không đụng. Không block
  nhau (core đã xong); chia sẻ files `deploy.py`, `monitor.py`, `_store.py`, `sync.js`.
- `260629-1125-hermes-ads-copilot`: infra dashboard (wire 5 chạm `infrastructure/` + `dashboard/`).

## Global Constraints
- **Money-safety giữ nguyên**: không path mới chi tiền. Changes = read/sync/notify
  + negatives (thêm criteria, không tăng spend) + optimize recommend-only.
- **Test mode verify**: test account API. CPA-threshold/smart-bidding paths
  verify sau Basic Access (test data mỏng).
- **KISS wire 2**: text-match keyword trong campaign (deploy tạo 1 ad group/campaign).
- **Files <200 lines** (code-standards): tách nếu monitor/optimize phình.
- **VND-native** (đã fix, không đụng).

## Phases
| # | Phase | Effort | Depends | Wires | File |
|---|-------|--------|---------|-------|------|
| A | Monitor data pipeline | 4h | — | 1, 2 | [phase-A](phase-A-monitor-data-pipeline.md) |
| B | Close optimize loop | 7.5h | A | 3, 4, 5 | [phase-B](phase-B-close-optimize-loop.md) |
| C | Deploy correctness | 4.5h | — | 6a, 6b, 6c | [phase-C](phase-C-deploy-correctness.md) |

Phase A+C độc lập (chạy song song được). Phase B phụ thuộc A (cần data thật).

## 8 Wires (tóm tắt)
1. `has_conversion_tracking` flag — derive từ env, reconcile giữ nguyên.
2. Keyword metrics — monitor sync thêm GAQL `keyword_view`.
3. optimize actions cụ thể, recommend-only.
4. Anomaly → Telegram (report channel, dedupe `alert_sent`).
5. Dashboard anomalies table (D1 + sync.js + panel).
6a. Negatives deploy (`deploy.py`).
6b. `MONTHLY_BUDGET` env stale fix + validation.
6c. UTC→account-local date consistency.

## Success Criteria (per phase)
- **A**: `monitor --mode sync` → `daily_metrics` có row `entity_type='keyword'`;
  campaign `has_conversion_tracking=1`.
- **B**: `optimize.py` console + `optimization_log` có action cụ thể; anomaly ping Telegram; dashboard hiển thị anomalies.
- **C**: `creator --approve --mock` log có negatives; `MONTHLY_BUDGET` env ≥1M.

## Risks (đầy đủ ở phase files)
- Test data mỏng → không trigger 30-conv/smart-bidding (verify sau Basic Access).
- Wire 5 chạm Workers infra → scope creep (Telegram wire 4 đã đủ skeleton).
- Env thật khả năng còn `MONTHLY_BUDGET=500` stale (money-safety).

## Next
`/cook plans/260702-0927-google-ads-flow-completion/` → bắt đầu Phase A.
Red-team tùy chọn: `/ck:plan red-team plans/260702-0927-google-ads-flow-completion/`.

## Completion (2026-07-02)
All 3 phases (A/B/C, 8 wires) implemented + code-reviewed (**APPROVE_WITH_NITS →
fixed**) + statically verified (compile + integration tests). Live GAQL verify
pending Developer Token (Test mode).

- **Phase A**: conversion flag derive+preserve; keyword metrics sync. ✓
- **Phase B**: concrete optimize actions (recommend-only); anomaly→Telegram
  (deduped); D1 anomalies table + sync.js + /api/anomalies + dashboard panel. ✓
- **Phase C**: campaign-level negatives deploy; MONTHLY_BUDGET 500→5,000,000 VND
  + ACCOUNT_CURRENCY=VND + <1M warn; account-local date boundary; SKILL.md
  Known Limitations updated. ✓
- **Code-review follow-ups applied**: `save_anomaly` idempotent per
  (entity,type,day) — no row accumulation during Telegram outage; sync.js
  anomaly inserts isolated per-row — one bad row no longer fails the whole sync.
- **Carry-over (not blocking)**: `_store.py` (771 LoC) + `monitor.py` (707 LoC)
  exceed the 200-line guide — pre-existing documented tech debt (see `_store.py`
  header); refactor deferred (out of scope, risky). D1 deploy of new
  `anomalies` table + sync.js/index.js/anomalies.js still needs `wrangler deploy`.
- Report: `plans/reports/code-reviewer-260702-google-ads-flow-completion.md`.
