# Phase B — Close Optimize Loop (wires 3, 4, 5)

## Context Links
- Plan: [`plan.md`](plan.md) | Brainstorm: `plans/reports/brainstormer-260702-0927-google-ads-flow-completion.md`
- Depends: [Phase A](phase-A-monitor-data-pipeline.md) (cần keyword metrics + conversion data)
- Files: `scripts/optimize.py`, `scripts/monitor.py`, `scripts/telegram_notify.py`, `scripts/sync_to_d1.py`, infra `infrastructure/schema.sql`, `infrastructure/src/sync.js`, `dashboard/`

## Overview
- **Priority:** P1 (đóng loop) | **Status:** complete | **Effort:** ~7.5h | **Depends:** A
- Khép vòng track→analyze→improve: optimize ra action cụ thể + log; anomaly ping
  Telegram; dashboard hiển thị anomalies.

## Key Insights
- `optimization_log` **đã tạo + INSERT** (`optimize.py:206`, `_ensure_optimization_log:41`).
  Chỉ cần đảm bảo mỗi recommendation → action cụ thể apply-able.
- `anomaly_log` + cờ `alert_sent` **đã có** (`monitor.py:384` gọi `save_anomaly`). Chỉ thiếu
  gọi Telegram sau save + set `alert_sent=1`.
- Wire 5 chạm infra `plans/260629-1125-hermes-ads-copilot/` (`schema.sql`, `src/sync.js`,
  `src/index.js`) + `dashboard/render-functions.js`/`dashboard.html` + `sync_to_d1.py`.

## Requirements
- **Func:** optimize → action cụ thể (PAUSE/ADD negative/SCALE), recommend-only, log;
  anomaly → Telegram (report channel) + dashboard; dedupe.
- **Non-func:** recommend-only (KHÔNG auto-mutate); idempotent alert (alert_sent).

## Architecture / Data Flow
```
optimize.py ──action cụ thể──► optimization_log (status=recommended)        [wire 3]
monitor.py ──save_anomaly──► telegram_notify.send_anomaly ──► report group  [wire 4]
                         ╲── set alert_sent=1 (dedupe)
anomaly_log ──sync_to_d1──► D1 anomalies ──► dashboard panel                [wire 5]
```

## Related Code Files
- **Modify (skill):** `scripts/optimize.py`, `scripts/monitor.py`, `scripts/telegram_notify.py`,
  `scripts/sync_to_d1.py`.
- **Modify (infra):** `plans/260629-1125-hermes-ads-copilot/infrastructure/schema.sql`,
  `.../src/sync.js`, `.../src/index.js`, `plans/260629-1125-hermes-ads-copilot/dashboard/render-functions.js`,
  `.../dashboard/dashboard.html`.
- **Read-only:** `scripts/daily_report.py` (pattern Telegram notify), `scripts/_store.py`.

## Implementation Steps
**Wire 3 — optimize actions:**
1. `optimize.py`: mỗi recommendation → dict `{entity_type, entity_id, action, reason, expected}`.
   Action chuẩn: `PAUSE_KEYWORD <keywords.id>`, `ADD_NEGATIVE <text>`, `SCALE_BUDGET <campaign_id> <±pct>`.
2. Status `recommended` khi log. **KHÔNG auto-apply** (money-safety). Thêm flag `--apply` = TODO (tactics phase).
3. Đảm bảo `_log_recommendations` INSERT đủ trường action.

**Wire 4 — anomaly → Telegram:**
4. `telegram_notify.py`: thêm `send_anomaly(anomaly_type, entity_name, metric, current, baseline, change_pct)`
   → report channel (dùng `_report_creds`, như `send_text`).
5. `monitor.py` sau `save_anomaly` (~line 392): gọi `send_anomaly(...)`, rồi `UPDATE anomaly_log SET alert_sent=1 WHERE rowid=?`.
6. Dedupe: skip nếu `alert_sent=1` đã có cho (entity+type+date). Wrap try/except (Telegram fail không block sync).

**Wire 5 — dashboard anomalies:**
7. `infrastructure/schema.sql`: thêm
   ```sql
   CREATE TABLE IF NOT EXISTS anomalies (
     detected_at TEXT, anomaly_type TEXT, entity_id TEXT, entity_name TEXT,
     metric_name TEXT, current_value REAL, baseline_value REAL, change_pct REAL, PRIMARY KEY(detected_at, entity_id, anomaly_type)
   );
   ```
8. `infrastructure/src/sync.js`: accept `anomalies` trong payload, INSERT/UPSERT.
9. `sync_to_d1.py`: push `SELECT * FROM anomaly_log WHERE alert_sent=1 AND synced_to_d1=0` (thêm cột synced_to_d1 cho anomaly_log nếu chưa).
10. `dashboard/`: thêm panel "Anomalies" (render-functions.js + tab/section html). Reuse style base.css.

## Todo List
- [ ] Wire 3: optimize action schema cụ thể + log đầy đủ
- [ ] Wire 3: recommend-only (không auto-apply)
- [ ] Wire 4: telegram_notify.send_anomaly (report channel)
- [ ] Wire 4: monitor gọi send_anomaly + alert_sent=1 + dedupe
- [ ] Wire 5: schema.sql anomalies table
- [ ] Wire 5: sync.js accept anomalies
- [ ] Wire 5: sync_to_d1 push anomalies
- [ ] Wire 5: dashboard panel
- [ ] Verify: optimize + synthetic anomaly + dashboard

## Success Criteria
- `optimize.py` console in action cụ thể (`PAUSE_KEYWORD 42`, …) + `optimization_log` có row status=`recommended`.
- Ép ngưỡng anomaly thấp (hoặc inject data) → Telegram report group nhận ping; `alert_sent=1`; re-run không ping lại.
- Dashboard hiển thị panel anomalies (D1 có data sau sync).

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| Wire 5 scope creep (chạm Workers+dashboard) | Med | Tách commit; wire 4 (Telegram) đã đủ skeleton nếu 5 trễ |
| Test data mỏng → optimize action ít ý nghĩa | Med | Verify cấu trúc; CPA-threshold paths đợi Basic Access |
| anomaly noise | Low | dedupe alert_sent + skip <7 ngày (đã có) |
| Telegram fail block sync | Low | try/except, log local |

## Security Considerations
- recommend-only: không mutate Google Ads ( KHÔNG chi tiền / tắt campaign tự động).
- Dashboard anomalies qua auth hiện có (JWT_SECRET). Không expose secret.

## Next Steps
- Phase C độc lập — có thể song song.
- `--apply` auto-pause (tactics phase) = TODO sau khi có 30 ngày data thật.
