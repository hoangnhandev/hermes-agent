# Phase 06 — Integration Testing + Documentation

## Context
- Parent: [plan.md](plan.md). Depends: Phase 04 (monitor skill operational), Phase 05 (dashboard deployed).
- Scenario criticals: end-to-end flow validation, all critical/high risks verified.
- Blocks: none (final phase).

## Overview
End-to-end integration testing of the full copilot pipeline: research → create → monitor →
dashboard → daily report. Verify each component works together, test failure scenarios,
and produce documentation (SKILL.md usage guide, env setup, quickstart).

## Key Insights
- **Integration tests are manual but structured**: with $500/mo budget, we can't run
  automated CI/CD tests against a live Google Ads account. Tests are documented
  checklists executed by the user, with expected vs actual results.
- **Test account is safe**: use the test campaign from Phase 00 (paused, $1/day).
  All creator/deploy tests target this. No real spend during testing.
- **Failure scenarios matter more than happy path**: verify sync failures, policy rejections,
  budget guardrails, empty states. These are the bugs that cause real damage.
- **Documentation is the deliverable**: SKILL.md must be complete enough that a new Hermes
  user can set up and run the copilot without reading these phase files.

## Requirements
- **Functional**: end-to-end test flow, failure scenario validation, documentation updates.
- **Non-functional**: test checklist document, env.example.md updated, quickstart guide created.

## Architecture
```
Testing Pipeline:
  1. Research (Phase 01)
     → Output: JSON plan file
     → Verify: valid JSON, all 4 sections present

  2. Create (Phase 03)
     → Input: research JSON
     → Verify: ad copy generated, policy screened, human approval flow works
     → Verify: API deployment succeeds (on test account)

  3. Monitor (Phase 04)
     → Input: created campaign
     → Verify: cron triggers, GAQL query returns data, local SQLite populated
     → Verify: D1 sync succeeds, dashboard shows data

  4. Dashboard (Phase 05)
     → Input: D1 data from sync
     → Verify: all 4 tabs render, KPIs correct, charts display

  5. Daily Report (Phase 04)
     → Input: local SQLite metrics
     → Verify: Telegram message delivers, KPIs accurate, suggestions present
```

## Related Code Files
- **Update**: `skills/research/google-ads/SKILL.md` (full usage guide)
- **Update**: `.env.example.md` or create new env reference
- **Create**: `skills/research/google-ads/docs/quickstart.md`
- **Create**: `plans/260629-1125-hermes-ads-copilot/reports/integration-test-results.md`
- **Read**: All phase files (00-05) for verification

## Interfaces

### Consumes
- All component outputs (research JSON, campaign IDs, D1 data, dashboard URL)
- Hermes cron schedule (verify active)
- Hermes Telegram gateway (verify alerts deliver)

### Produces
- `reports/integration-test-results.md` — pass/fail for each test
- Updated `SKILL.md` — complete usage guide
- `docs/quickstart.md` — new user onboarding
- Updated env reference

## Implementation Steps

### Step 1: End-to-End Happy Path Test (1h)

```
TEST 1: Research → JSON Output
  $ python3 scripts/research.py --niche "test niche" --budget 500
  Expected: data/google-ads-research-{date}.json created
  Verify: JSON valid, contains keywords[], competitors[], audience{}, budget_plan{}
  Result: PASS / FAIL

TEST 2: Creator → Ad Copy Generation
  $ python3 scripts/creator.py --plan data/google-ads-research-{date}.json
  Expected: 10-15 ad copy variations printed to terminal
  Verify: each has headlines[], descriptions[], policy.passed flag
  Result: PASS / FAIL

TEST 3: Policy Screening
  Verify: copy with "guaranteed" rejected
  Verify: copy with 35-char headline rejected
  Verify: clean copy passes
  Result: PASS / FAIL

TEST 4: Human Approval Flow
  Enter selection: "1,3,5"
  Expected: only variations 1, 3, 5 deployed
  Result: PASS / FAIL

TEST 5: Campaign Deployment (Test Account)
  Expected: campaign created in Google Ads UI
  Expected: campaign appears with status "Eligible"
  Expected: D1 sync POST /api/sync → 200
  Result: PASS / FAIL

TEST 6: Monitor Sync (Manual Trigger)
  $ python3 scripts/monitor.py full
  Expected: GAQL query returns metrics for test campaign
  Expected: local SQLite has rows in daily_metrics
  Expected: D1 has matching rows (verify via GET /api/metrics)
  Result: PASS / FAIL

TEST 7: Dashboard Renders
  Open dashboard URL in browser
  Expected: login page → enter password → dashboard loads
  Expected: Tab 1 (Campaign Overview) shows test campaign KPIs
  Expected: Tab 4 (Budget Tracking) shows budget progress
  Result: PASS / FAIL

TEST 8: Daily Report
  $ python3 scripts/daily_report.py
  Expected: Telegram message delivered
  Expected: contains KPIs, top/bottom performers, suggestions
  Result: PASS / FAIL
```

### Step 2: Failure Scenario Tests (45 min)

```
TEST 9: Empty Dashboard
  Fresh D1 (no data) → open dashboard
  Expected: "No data yet" on all 4 tabs
  Expected: no JavaScript errors
  Result: PASS / FAIL

TEST 10: Budget Guardrail
  Attempt to create campaign with daily_budget > monthly/30*2
  Expected: rejected with error message
  Expected: no campaign created
  Result: PASS / FAIL

TEST 11: Sync Failure + Retry
  Temporarily break D1 endpoint (change URL)
  Expected: retry 3x with exponential backoff
  Expected: sync_status records failure
  Expected: after 3 consecutive runs, Telegram alert sent
  Restore endpoint → run sync → verify recovery
  Result: PASS / FAIL

TEST 12: Policy Screening Rejection
  Generate copy with disallowed terms
  Expected: policy_check rejects with violation list
  Expected: variation NOT shown in approval queue
  Result: PASS / FAIL

TEST 13: Auth — Wrong Password
  Enter wrong password on login page
  Expected: "Invalid password" error, no redirect
  Result: PASS / FAIL

TEST 14: Auth — Token Expiry
  Manually expire JWT (short expiry for test)
  Expected: auto-refresh attempt
  Expected: if refresh fails, redirect to login
  Result: PASS / FAIL

TEST 15: Orphan Campaign
  Delete test campaign in Google Ads UI manually
  Run monitor sync
  Expected: campaign marked "archived" in D1
  Expected: historical metrics preserved
  Result: PASS / FAIL

TEST 16: Cron Verification
  Check Hermes cron schedule
  Expected: monitor.py full every 6 hours
  Expected: daily_report.py at 9am daily
  Verify logs show recent executions
  Result: PASS / FAIL
```

### Step 3: Documentation Updates (45 min)

**SKILL.md update** — add complete usage guide:
```markdown
## How to Run

### 1. Research (no API needed)
```
/google-ads research --niche "web design agency" --location "Austin, TX" --budget 500
```
Output: `data/google-ads-research-2026-06-29.json`

### 2. Create Campaign (needs API credentials)
```
/google-ads create --plan data/google-ads-research-2026-06-29.json
```
Flow: generate copy → policy screen → human approval → deploy

### 3. Monitor (automatic via cron, or manual)
```
/google-ads monitor sync    # manual sync trigger
/google-ads monitor report   # manual daily report
```

### 4. View Dashboard
Open: https://ads-copilot-dashboard.pages.dev
Login with password configured in Workers secrets.

### Environment Variables
See `google-ads.env.example` for all required variables.

### Cron Schedule
- Every 6h: full sync + anomaly detection
- Daily 9am: Telegram daily report
```

**Env reference** (`google-ads.env.example`):
```bash
# Google Ads API
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_REFRESH_TOKEN=
GOOGLE_ADS_CUSTOMER_ID=
GOOGLE_ADS_LOGIN_CUSTOMER_ID=
GOOGLE_ADS_CONVERSION_ACTION_ID=

# Budget (NEVER change these without code review)
MONTHLY_BUDGET=500
MAX_DAILY_MULTIPLIER=2

# Cloudflare Workers (for D1 sync)
WORKERS_API_URL=https://ads-copilot-api.<subdomain>.workers.dev
HERMES_SYNC_SECRET=

# Hermes Telegram
TELEGRAM_CHAT_ID=
```

**Quickstart guide** (`docs/quickstart.md`):
```markdown
# Hermes Ads Copilot — Quickstart

## Prerequisites
1. Google Ads account with billing (Phase 00)
2. Landing page with lead form + Google Tag installed
3. Hermes Agent running on VPS

## Setup (30 min)
1. Complete Phase 00 (account + API setup)
2. Set up env vars: cp google-ads.env.example google-ads.env → fill values
3. Install deps: source .venv-google-ads/bin/activate && pip install -r google-ads-requirements.txt
4. Initialize local DB: python3 scripts/monitor.py init

## First Campaign (15 min)
1. Research: /google-ads research --niche "your niche" --budget 500
2. Review output JSON → edit if needed
3. Create: /google-ads create --plan data/google-ads-research-{date}.json
4. Approve ad copy variations when prompted
5. Dashboard: open https://ads-copilot-dashboard.pages.dev

## Monitoring (automatic)
- Cron syncs every 6 hours
- Daily report at 9am via Telegram
- Anomaly alerts sent immediately on detection

## Troubleshooting
- Sync failures → check HERMES_SYNC_SECRET matches Workers secret
- No data in dashboard → verify cron is active, check D1 sync status
- Auth errors → verify JWT_SECRET, try clearing cookies
```

### Step 4: Monitoring Verification (15 min)

```
Verify cron jobs:
  $ crontab -l | grep google-ads
  Expected:
    0 */6 * * * .../scripts/monitor.py full
    0 9 * * * .../scripts/daily_report.py

Verify cron logs:
  $ grep google-ads /var/log/syslog | tail -20
  Expected: recent entries for monitor.py and daily_report.py

Verify Telegram alerts:
  Send test alert → verify delivery
  Expected: message appears in configured chat

Verify Workers API health:
  $ curl -s https://ads-copilot-api.<subdomain>.workers.dev/api/auth/login -X POST
  Expected: 400 (missing password) — confirms Workers is alive
```

## Todo
- [ ] Execute Test 1-8 (happy path) → record results
- [ ] Execute Test 9-16 (failure scenarios) → record results
- [ ] Fix any failing tests before proceeding
- [ ] Update SKILL.md with complete usage guide
- [ ] Create/update google-ads.env.example
- [ ] Create docs/quickstart.md
- [ ] Verify cron schedule active
- [ ] Verify Telegram alerts deliver
- [ ] Verify Workers API responding
- [ ] Write integration-test-results.md with pass/fail summary

## Success Criteria
- All 16 tests pass (or failures documented with root cause)
- SKILL.md contains full usage guide (research, create, monitor, dashboard)
- google-ads.env.example lists all required variables with descriptions
- Quickstart guide enables new user setup in <30 min
- Cron jobs verified active (every 6h sync, daily 9am report)
- Telegram alerts deliver successfully
- Dashboard accessible and rendering real data
- No silent failures in any component

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| Integration test reveals data mismatch between local SQLite and D1 | Med | Resync tool: POST all local data to D1. Add reconciliation endpoint. |
| Cron not running ( Hermes scheduler issue) | High | Verify crontab + test manual trigger. Add cron health check to daily report. |
| Telegram alerts not delivering | Med | Verify gateway credentials. Test with simple message first. |
| Documentation incomplete for new user | Low | Quickstart guide tested by someone unfamiliar with the system. |
| Google Ads API returns unexpected data format (version drift) | Med | Pin library version. Log raw responses for debugging. |

## Security
- No credentials in documentation
- Env example files contain placeholder values only
- Test account only (no real spend during testing)
- Dashboard password not shared in docs

## Next Steps
- None — this is the final phase
- Post-MVP: Smart Bidding (after 30+ conversions), Facebook Ads integration, CRM integration
