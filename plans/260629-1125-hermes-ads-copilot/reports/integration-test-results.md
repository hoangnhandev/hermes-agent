# Hermes Ads Copilot — Integration Test Results

## Test Execution Date: YYYY-MM-DD
## Google Ads Account: [Your Customer ID]
## Developer Token: [Test Mode | Basic Access]

---

## Happy Path Tests (Tests 1-8)

- [ ] **Test 1: Research → JSON Output** — Verify JSON valid, all 4 sections present
- [ ] **Test 2: Creator → Ad Copy Generation** — 10-15 variations printed
- [ ] **Test 3: Policy Screening** — Disallowed terms rejected, character violations rejected
- [ ] **Test 4: Human Approval Flow** — User selects → only selected deployed
- [ ] **Test 5: Campaign Deployment (Test Account)** — Campaign created, D1 synced
- [ ] **Test 6: Monitor Sync (Manual)** — GAQL returns data, local SQLite populated, D1 synced
- [ ] **Test 7: Dashboard Renders** — 4 tabs load, KPIs correct, charts display
- [ ] **Test 8: Daily Report** — Telegram delivers, KPIs accurate, suggestions present

## Failure Scenario Tests (Tests 9-16)

- [ ] **Test 9: Empty Dashboard** — Fresh D1 → "No data yet" on all tabs
- [ ] **Test 10: Budget Guardrail** — Exceed cap → rejected, no campaign created
- [ ] **Test 11: Sync Failure + Retry** — 3 retries with 5s/25s/125s, alert after 3 consecutive
- [ ] **Test 12: Policy Screening Rejection** — Disallowed terms → not shown in approval
- [ ] **Test 13: Auth — Wrong Password** — Error message, no redirect
- [ ] **Test 14: Auth — Token Expiry** — Auto-refresh attempt, redirect to login on fail
- [ ] **Test 15: Orphan Campaign** — Deleted in UI → marked archived in D1
- [ ] **Test 16: Cron Verification** — crontab shows jobs, logs show recent executions

## Summary

**Total Tests:** 16
**Passed:** 0
**Failed:** 0
**Skipped:** 16 (Pending Google Ads account setup)