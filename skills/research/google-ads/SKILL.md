---
name: google-ads-research
description: "Google Ads skill for Vinfast (VN): budget-aware strategy generator (deterministic benchmarks) + campaign creator/monitor/optimize. LLM enhancement layered by agent on top of deterministic spine."
version: 0.1.0
author: Hermes Agent
tags: [google-ads, keyword-research, competitor-analysis, hermes-skill]
platforms: [linux, macos, windows]
---

# Google Ads Research & Creator Skill

## When to Use

Use this skill when you need comprehensive Google Ads research including:
- Keyword research with search volume and competition analysis
- Competitor analysis and positioning insights
- Audience targeting recommendations
- Budget planning and performance estimates
- Campaign creation with Google Ads API integration
- Ad copy generation with policy screening

## Prerequisites

- Hermes Agent with web search capabilities
- Access to LLM reasoning (provided by Hermes runtime)
- No Google Ads API key required for research (deterministic benchmarks from `references/`; the agent layers LLM reasoning on the `--json` output)
- Google Ads API credentials required for campaign creation

## How to Run

### Research Only (budget-aware strategy generator)
```bash
# Budget-aware strategy — Vinfast VF3 (default), Vietnam market.
# Budget in VND. Outputs honest projections (clicks → leads → sales) + tier + keyword seeds.
python3 scripts/research.py --budget 10000000 --model vf3

# With honest goal check (warns if budget can't hit goal_sales/month)
python3 scripts/research.py --budget 10000000 --model vf3 --goal-sales 2

# Other models: vf3 vf5 vf6 vf7 vf8 vf9  | JSON output for agent/pipe
python3 scripts/research.py --budget 5000000 --model vf5 --json
```
**Note:** research.py is the deterministic spine (benchmarks from `references/automotive-benchmarks.md`).
LLM enhancement (ad-copy angles, keyword expansion) is layered by the agent on top of the JSON output.
Old `--niche/--location` plumbing-style CLI is removed — this skill is Vinfast-automotive focused.

### Campaign Creation (requires research plan + Google Ads creds)
```bash
# Create campaign from a research strategy file (output of research.py)
python3 scripts/creator.py --plan data/strategy-vf3-2026-06-30.json

# Dry-run with mock Google Ads client (no real deploy, no spend)
python3 scripts/creator.py --plan data/strategy-vf3-2026-06-30.json --mock
```
**Note:** `creator.py` requires `--plan` (inline research not implemented).
Approval is async (Phase 03 built): `creator.py --plan X` writes a pending
record + notifies Telegram + exits (cron-safe). Resume via
`creator.py --approve <uuid> --indices 1,3` to deploy (or `--reject <uuid>`).

## Research Capabilities

### Keyword Research
- Deterministic keyword seeds (branded/non-branded/intent/competitor/negative) from `references/automotive-keyword-taxonomy.md`
- Vinfast VF-focused (VF3 default); expandable to vf5/vf6/vf7/vf8/vf9
- Full taxonomy + Vietnamese variants in references (agent can layer LLM expansion)
- Estimates competition levels and suggested bids
- Recommends match types (defaults to phrase for new accounts)

### Competitor Analysis
- Identifies top 5 competitors in the niche
- Analyzes competitor positioning and messaging
- Identifies competitive gaps and opportunities
- Provides strategic recommendations

### Audience Targeting
- Recommends demographic targeting
- Suggests geographic targeting options
- Identifies relevant interests and behaviors
- Aligns with campaign goals

### Budget Planning
- Calculates daily and maximum daily budgets
- Estimates monthly clicks and leads
- Provides cost-per-click and cost-per-lead estimates
- Recommends bidding strategies

### Automotive Domain Knowledge (Vinfast/EV)
- **Industry Benchmarks:** $2.41 CPC, 7.76% CVR, $38.86 CPL (automotive vs. general $5.26 CPC, 7.52% CVR, $70.11 CPL)
- **Market-Aware CPC:** US/global automotive $2.41 CPC; **VN ~$0.50** (range $0.30-0.80, ~76% below US — leadsoff 2025). `--market vn` (default) uses VN CPC; `--market global` uses US for comparison. CVR + lead→sale remain global benchmarks (VN-specific data scarce → treat projected sales as an upper bound).
- **EV Marketing Nuances:** Range/charge anxiety messaging, infrastructure confidence, TCO focus
- **Vinfast Positioning:** Vietnam #1 EV brand, 10-year warranty, battery lease, national brand pride
- **Budget Realism:** $500/month insufficient for automotive (min $1.5K, rec $3K-8K, aggressive $8K+)
- **Phased Strategy:** Launch (months 1-2) → Optimize (3-4) → Scale (5-12) with KPIs per phase
- **Keyword Taxonomy:** Branded (1299% ROAS) vs. non-branded (68% ROAS) vs. competitor conquest
- **Audience Strategy:** In-market auto intenders, EV researchers, remarketing (website visitors, YouTube viewers)
- **Ad Formats:** Responsive Search Ads, extensions (sitelinks, callouts, location), Performance Max Vehicle Ads
- **Conversion Tracking:** Test-drive booking (primary), brochure download (secondary), offline import (30-90 day lag)

## Output Format

The skill generates a comprehensive JSON report containing:
- **Keywords**: List with search volume, competition, intent, CPC estimates
- **Competitors**: Analysis of top 5 competitors with positioning insights
- **Audience**: Demographic, geographic, and interest targeting recommendations
- **Budget Plan**: Daily budgets, performance estimates, and bidding strategy
- **Automotive-Specific Outputs** (if automotive niche detected):
  - Budget tier recommendation (minimum viable / recommended / aggressive)
  - Phased long-term strategy (12-month roadmap with KPIs per phase)
  - Keyword taxonomy (branded/non-branded/competitor + negative list starter)
  - EV messaging guidelines (range reassurance, charging convenience, warranty)
  - Audience + retargeting playbook (in-market, remarketing, life events)

Outputs are saved to `data/strategy-{model-slug}-{YYYY-MM-DD}.json` (e.g. `strategy-vf3-2026-06-30.json`) with a summary in the console.

## Campaign Creation

### Process Flow

1. Generates ad copy variations (currently template-based placeholders; real Vinfast-relevant copy via agent-layered LLM is planned — see `generate_ad_copy` TODO)
2. Policy screening rejects obvious violations before human review
3. User approves specific variations (e.g., "1,3,5,8")
4. Campaign deployed via Google Ads API (Search, Manual CPC)
5. Ad groups, keywords, and ads created in batches
6. Campaign structure synced to D1 dashboard

### Budget Guardrails

- Per-campaign: `max_daily = campaign_monthly_budget / 30 * 2`
- Account total: all active campaigns' daily budgets must not exceed `total_monthly_budget / 30 * 2`
- Hardcoded in code — cannot be overridden by LLM
- Creation blocked if guardrails violated

### Policy Screening

Automatic screening against Google Ads policy:
- Disallowed terms (guaranteed, #1, cure, etc.)
- Character limits (headline 30, description 90)
- Conditional terms (free — marked as warning, not rejection)
- Human approval is final gate — system never auto-deploys

### Ad Copy Learning

All ad copy variations (approved and rejected) are stored in a local SQLite database for:
- Performance analysis and optimization
- Learning which copy performs best
- Avoiding repeated policy violations
- Future LLM training data

### Google Ads API Integration

Campaign creation requires:
- Google Ads developer token
- Google Ads manager account
- Customer ID for the target Google Ads account
- OAuth2 credentials with appropriate permissions

The system includes:
- Mock client for development without credentials
- Batch processing for keywords and ads (groups of 10)
- Retry logic for rate limits (GoogleAdsException RESOURCE_EXHAUSTED, exp backoff)
- Comprehensive error handling

## Monitoring Capabilities

> **⚠️ ALPHA — not yet verified against a live Google Ads API account.**
> The cred-loading bugs from the first prototype (`load_from_storage` vs
> `load_from_env`, `login_customer_id` vs `customer_id`, `datetime.utcnow`)
> are **fixed**. What remains unverified is end-to-end: the GAQL query logic
> is real but has never run against a live account, so results may be wrong
> in ways static review can't catch. **Run only against a Google Ads test
> account** until verified against live data.

### Automated Monitoring

The skill includes comprehensive monitoring capabilities for ongoing campaign performance:

```bash
# Run full sync and monitoring cycle
python3 scripts/monitor.py --mode full

# Sync data from Google Ads API only
python3 scripts/monitor.py --mode sync

# Generate daily report only
python3 scripts/monitor.py --mode report

# Run anomaly detection only
python3 scripts/monitor.py --mode detect
```

## Optimization Capabilities (monthly review loop)

After `monitor.py` has collected ≥30 days of `daily_metrics`, run `optimize.py`
for a period-over-period review + actionable plan for the next month. Same
track → analyze → improve loop as polymarket-signals calibration.

```bash
# Last 30d vs previous 30d, keyword-level (default, most actionable)
python3 scripts/optimize.py

# Campaign/ad_group level, custom period
python3 scripts/optimize.py --entity campaign --days 30

# JSON for agent/pipe (recommended: agent layers LLM reasoning on top)
python3 scripts/optimize.py --json
```

**Output per run:** period summary vs baseline (clicks/cost/conv/CVR/CPA deltas),
🏆 top performers (→ SCALE), 🗑️ wasted spend (→ PAUSE/negative), CVR-drop watch,
and a concrete action plan. Actions are logged to `optimization_log` table
(for impact tracking next run). Run monthly (cron) after the campaign matures.

### Data Flow Architecture

The monitoring system follows a robust data flow:

1. **Google Ads API** → Query campaigns, metrics, and leads via GAQL
2. **Local SQLite** → Source of truth for all metrics and anomalies (`campaigns-local.db`)
3. **Cloudflare D1** → Replica for dashboard and reporting (synced with retry logic)
4. **Telegram Alerts** → daily reports only (anomaly pings: **local log only, NOT yet wired to Telegram**)

### Sync Protocol

Automated synchronization ensures data consistency:

- **Frequency**: Can be run via cron (recommended: every 15-30 minutes during business hours)
- **Retry Logic**: MAX_RETRIES=3 with exponential backoff (5s, 10s, 20s)
- **Error Handling**: Tracks consecutive failures (alerts are logged locally; Telegram pings NOT yet wired)
- **Data Integrity**: Reconciles orphan campaigns (marks as archived if deleted externally)

GAQL query for metrics:
```sql
SELECT campaign.id, campaign.name, campaign.status, segments.date,
       metrics.impressions, metrics.clicks, metrics.cost_micros,
       metrics.conversions, metrics.conversions_value
FROM campaign
WHERE segments.date >= '{date_range}' AND campaign.status = 'ENABLED'
ORDER BY segments.date DESC, campaign.id
```

### Anomaly Detection

> ⚠️ Detected anomalies are written to the local `anomaly_log` table **only**.
> Telegram pings for anomalies are NOT yet wired (TODO in `monitor.py`).
> Daily performance reports ARE sent to Telegram. Do not rely on anomaly
> alerts reaching your phone yet.

Multi-campaign anomaly detection with intelligent baselines:

**Detection Rules:**
- **CPA Spike**: >30% increase in cost per acquisition (campaigns with conversion tracking only)
- **CTR Drop**: >20% decrease in click-through rate
- **Spend Pacing**: >2x daily budget utilization

**Smart Filtering:**
- Skip campaigns <7 days old (insufficient baseline data)
- Skip CPA checks for campaigns without `has_conversion_tracking=1`
- Per-campaign baselines (not account-wide averages)

**LLM Analysis** (TODO): Anomaly analysis and recommendations via Hermes LLM integration

### Daily Reporting

Automated daily performance reports sent to Telegram:

**Per-Campaign Format:**
```markdown
✅ *Campaign A* (leads)
   Clicks: 150 | CTR: 3.2% | Leads: 12 | CPL: $13.89
   Budget: $15.00/$16.67 daily (90%)
```

**Report Contents:**
- Account-level summary (impressions, clicks, CTR, cost, leads, CPL)
- Per-campaign breakdown with KPIs and pacing
- Campaigns without conversion tracking show impressions/clicks/spend (no leads/CPL)
- Top 5 performing keywords across all campaigns
- Per-campaign LLM optimization suggestions (TODO)

**Telegram Integration:**
- Markdown formatted messages
- Configurable bot token and chat ID
- Automatic daily delivery (recommended: 9 AM local time)

### Database Schema

The monitoring system extends the existing schema:

```sql
-- Daily Metrics (stores performance data)
CREATE TABLE daily_metrics (
    entity_type TEXT NOT NULL,    -- 'campaign', 'keyword', etc.
    entity_id TEXT NOT NULL,
    date TEXT NOT NULL,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    cost REAL DEFAULT 0.0,
    conversions INTEGER DEFAULT 0,
    conversion_value REAL DEFAULT 0.0,
    synced_to_d1 INTEGER DEFAULT 0,
    UNIQUE(entity_type, entity_id, date)
);

-- Anomaly Log (stores detected anomalies)
CREATE TABLE anomaly_log (
    detected_at TEXT DEFAULT (datetime('now')),
    anomaly_type TEXT NOT NULL,     -- 'CPA_SPIKE', 'CTR_DROP', etc.
    entity_id TEXT,
    entity_name TEXT,
    metric_name TEXT NOT NULL,
    current_value REAL,
    baseline_value REAL,
    change_pct REAL,
    llm_analysis TEXT,            -- TODO: LLM analysis
    alert_sent INTEGER DEFAULT 0
);
```

### Files Structure

```
scripts/
├── monitor.py             # Main orchestrator with cron modes
├── sync_to_d1.py          # D1 sync with retry logic
├── daily_report.py        # Telegram daily report generator
├── _store.py              # Updated with monitoring functions
├── research.py            # Existing (Phase 01)
├── creator.py             # Existing (Phase 03)
├── deploy.py              # Existing (Phase 03)
└── policy_check.py        # Existing (Phase 03)

data/
├── campaigns-local.db     # Source of truth for all metrics
├── sync-status.json       # Last sync state + failure tracking
└── anomaly-alerts.log     # Append-only anomaly history

## Quickstart Guide

### Prerequisites

1. **Google Ads Account** with billing setup
2. **Google Cloud Project** with Google Ads API enabled
3. **OAuth 2.0 Credentials** (Client ID, Client Secret)
4. **Developer Token** (Test Mode OK for dev, Basic Access for prod)
5. **Conversion Action** ID (setup in Google Ads UI)
6. **Cloudflare Account** with D1 + Workers + Pages
7. **Hermes Agent** running on VPS with Telegram gateway

### Setup (30 min)

1. **Install Dependencies** (on Hermes VPS):
```bash
cd ~/hermes-agent/skills/research/google-ads
python3 -m venv .venv
source .venv/bin/activate
pip install google-ads requests
```

2. **Create Environment File**:
```bash
cp google-ads.env.example google-ads.env
# Fill in your values
```

3. **Initialize Local Database**:
```bash
python3 scripts/_store.py init
```

### First Campaign (15 min)

1. **Research** (budget-aware strategy — Vinfast VF3 default, Vietnam market):
```bash
python3 scripts/research.py --budget 10000000 --model vf3 --goal-sales 2
```
Budget in VND. Honest projections + tier + keyword seeds.
Output: `data/strategy-vf3-{date}.json`

2. **Review + Create** (interactive — NOT cron-safe; needs Google Ads creds):
```bash
python3 scripts/creator.py --plan data/strategy-vf3-{date}.json
# Dry-run (no creds, no spend): add --mock
```
- Budget guardrail checked (MONTHLY_BUDGET env cap)
- Policy screening on ad copy
- Interactive approval (`input()`) — approve variations by number (e.g. "1,3,5")
- Deploys via `deploy.deploy_full_campaign` (REAL) — or `--mock` dry-run
- **Cron/non-tty runs abort cleanly without deploying** (async `--approve` gate built, Phase 03)
- **Anomaly alerts = LOCAL log only** (anomaly_log table). Anomalies are NOT synced to D1/Telegram yet (Workers /api/sync has no anomalies table); monitor logs them locally. Wire Telegram anomaly pings + D1 anomalies table in a future phase.

3. **Monitor** (automatic via cron, or manual):
```bash
python3 scripts/monitor.py --mode full
python3 scripts/daily_report.py
```

4. **View Dashboard**:
Open: https://ads-copilot-dashboard.pages.dev
Login with DASHBOARD_PASSWORD

### Cron Schedule

Add to Hermes cron:
```bash
0 */6 * * * cd ~/hermes-agent/skills/research/google-ads && .venv/bin/python3 scripts/monitor.py --mode full
0 9 * * * cd ~/hermes-agent/skills/research/google-ads && .venv/bin/python3 scripts/daily_report.py
```

### Troubleshooting

- **Sync failures**: Check HERMES_SYNC_SECRET matches Workers secret
- **No data in dashboard**: Verify cron is active, check D1 sync status
- **Auth errors**: Verify JWT_SECRET, try clearing cookies
- **API rate limit**: Check budget, adjust batch size in deploy.py

## ⚠️ Known Limitations (verified by adversarial review)

Honest gaps surfaced by multi-round review. None are silent lies — listed so
you know exactly what does NOT work yet:

- **CPA-spike anomaly detection won't fire** until conversion tracking is
  wired: `has_conversion_tracking` is never set to 1, and `reconcile_campaigns`
  resets it to 0 each sync. The CPA/CTR/pacing rules exist but gate on this
  flag, so they are currently inert. (monitor.py — ALPHA)
- **"Top Keywords" report section renders empty**: monitor collects
  campaign-level metrics only, not keyword-level. Add keyword metrics before
  this section is meaningful. (daily_report.py — ALPHA)
- **Negative keywords are NOT applied at deploy**: research emits a negative
  list (`vf3 cũ`, `review vf3`, …) but `deploy.py` bids on positive keywords
  only. Negatives will be wired as campaign/ad-group criteria in a future phase.
- **Currency is assumed USD**: budgets/cost use USD micros (`amount_micros`).
  At go-live, confirm the account's `currency_code` — if VND-billed, amounts
  need a conversion factor.
- **Date math is UTC**: GAQL `segments.date` is account-local. If the account
  `time_zone` ≠ UTC (VN is UTC+7), daily-report day boundaries shift by the
  offset. Confirm/adjust at go-live.
- **Anomaly → Telegram pings not wired** (anomalies are local-log only; see
  Anomaly Detection section above).

Research/strategy path (`research.py` + `_budget_calc.py`) has none of these
gaps — it is pure deterministic math, verified, and the recommended entry point
until you have a real Google Ads token.



When you have real Google Ads credentials, this exact sequence takes the skill live:

### 1. Fill `google-ads.env` (copy from `google-ads.env.example`)
```
GOOGLE_ADS_CLIENT_ID=...           # OAuth client (Google Cloud Console)
GOOGLE_ADS_CLIENT_SECRET=...
GOOGLE_ADS_DEVELOPER_TOKEN=...     # starts in TEST mode (test accounts only)
GOOGLE_ADS_REFRESH_TOKEN=...       # from OAuth flow
GOOGLE_ADS_CUSTOMER_ID=1234567890  # the CHILD account to query (no dashes)
GOOGLE_ADS_LOGIN_CUSTOMER_ID=...   # MCC manager (same as customer_id if no MCC)
GOOGLE_ADS_CONVERSION_ACTION_ID=...
MONTHLY_BUDGET=500                 # account spend cap in USD (NOT VND — guardrail enforces; warns if >$100k, likely VND-as-USD typo)
WORKERS_API_URL=https://ads-copilot-api.<your>.workers.dev
HERMES_SYNC_SECRET=<random>        # MUST match Workers secret
TELEGRAM_CHAT_ID=<your_chat_id>    # for approval requests + reports
```
⚠️ **CUSTOMER_ID vs LOGIN_CUSTOMER_ID**: `CUSTOMER_ID` = the account holding
campaigns (queried by monitor). `LOGIN_CUSTOMER_ID` = the MCC manager (only
differs if you use a manager account). Skill uses `CUSTOMER_ID` for GAQL.

### 2. Install the Google Ads client lib
```bash
cd ~/hermes-agent/skills/research/google-ads
pip install google-ads requests
```

### 3. Verify each piece (against a TEST account first!)
```bash
# Strategy (no creds needed): honest projections
python3 scripts/research.py --budget 10000000 --model vf3 --goal-sales 2

# Monitor (reads API): should list real campaigns
python3 scripts/monitor.py --mode sync

# Creator → approval gate (headless): writes pending, notifies Telegram
python3 scripts/creator.py --plan data/strategy-vf3-<date>.json

# Approve + deploy (REAL — spends money!): run the command Telegram sent you
python3 scripts/creator.py --approve <uuid> --indices 1,3

# Sync to D1 dashboard
python3 scripts/sync_to_d1.py

# Monthly review
python3 scripts/optimize.py
```

### 4. Dry-run before spending (mock deploy, no API hit)
```bash
python3 scripts/creator.py --plan data/strategy-vf3-<date>.json   # create mode
python3 scripts/creator.py --approve <uuid> --indices 1,3 --mock  # mock deploy
```

### 5. Go live
- Switch Developer Token to **Basic Access** (Google review) for prod spend.
- Set cron (see Cron Schedule above).
- First `optimize.py` run after 30 days of data.

### Common go-live pitfalls
- **`GOOGLE_ADS_CUSTOMER_ID not set`** → monitor queries return empty (M2 fix).
- **Test-account mode** → Developer Token in TEST mode can only manage test
  accounts; prod needs Basic Access.
- **`HERMES_SYNC_SECRET` mismatch** → sync 401s; must equal Workers secret.
- **Telegram not set** → approval requests skipped (creator still writes pending;
  read the uuid from stdout).
```