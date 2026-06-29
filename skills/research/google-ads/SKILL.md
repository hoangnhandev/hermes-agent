---
name: google-ads-research
description: "Google Ads research skill: keyword, competitor, audience, budget analysis via web search + LLM"
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
- No Google Ads API key required for research (uses web search + LLM analysis)
- Google Ads API credentials required for campaign creation

## How to Run

### Research Only
```bash
# Basic research with default settings
python3 scripts/research.py --niche "plumbing services"

# With custom location and budget
python3 scripts/research.py --niche "dentist" --location "New York" --budget 1000 --goal "appointments"
```

### Campaign Creation
```bash
# Create campaign from research plan
python3 scripts/creator.py --plan data/google-ads-research-2026-06-29.json

# Or inline research + creation
python3 scripts/creator.py --niche "web design agency" --location "Austin, TX" --budget 500
```

## Research Capabilities

### Keyword Research
- Generates seed keywords based on niche and location
- Expands keywords via web search
- Classifies search intent (transactional/informational/navigational)
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

## Output Format

The skill generates a comprehensive JSON report containing:
- **Keywords**: List with search volume, competition, intent, CPC estimates
- **Competitors**: Analysis of top 5 competitors with positioning insights
- **Audience**: Demographic, geographic, and interest targeting recommendations
- **Budget Plan**: Daily budgets, performance estimates, and bidding strategy

Outputs are saved to `data/google-ads-research-{YYYY-MM-DD}.json` with a summary presented in the console.

## Campaign Creation

### Process Flow

1. LLM generates 10-15 ad copy variations based on research plan
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
- Retry logic for rate limits (429 errors)
- Comprehensive error handling

## Monitoring Capabilities

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

### Data Flow Architecture

The monitoring system follows a robust data flow:

1. **Google Ads API** → Query campaigns, metrics, and leads via GAQL
2. **Local SQLite** → Source of truth for all metrics and anomalies (`campaigns-local.db`)
3. **Cloudflare D1** → Replica for dashboard and reporting (synced with retry logic)
4. **Telegram Alerts** → Real-time anomaly notifications and daily reports

### Sync Protocol

Automated synchronization ensures data consistency:

- **Frequency**: Can be run via cron (recommended: every 15-30 minutes during business hours)
- **Retry Logic**: MAX_RETRIES=3 with exponential backoff (5s, 10s, 20s)
- **Error Handling**: Tracks consecutive failures and alerts after 3+ failures
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

1. **Research**:
```bash
python3 scripts/research.py --niche "web design agency" --location "Austin, TX" --budget 500
```
Output: `data/google-ads-research-{date}.json`

2. **Review + Create**:
```bash
python3 scripts/creator.py --plan data/google-ads-research-{date}.json --budget 500
```
- Review ad copy variations
- Enter approved numbers (e.g., "1,3,5")
- Confirm deployment

3. **Monitor** (automatic via cron, or manual):
```bash
python3 scripts/monitor.py full
python3 scripts/daily_report.py
```

4. **View Dashboard**:
Open: https://ads-copilot-dashboard.pages.dev
Login with DASHBOARD_PASSWORD

### Cron Schedule

Add to Hermes cron:
```bash
0 */6 * * * cd ~/hermes-agent/skills/research/google-ads && .venv/bin/python3 scripts/monitor.py full
0 9 * * * cd ~/hermes-agent/skills/research/google-ads && .venv/bin/python3 scripts/daily_report.py
```

### Troubleshooting

- **Sync failures**: Check HERMES_SYNC_SECRET matches Workers secret
- **No data in dashboard**: Verify cron is active, check D1 sync status
- **Auth errors**: Verify JWT_SECRET, try clearing cookies
- **API rate limit**: Check budget, adjust batch size in deploy.py
```