# Phase 04 — Hermes Skill: google-ads-monitor

## Context
- Parent: [plan.md](plan.md). Depends: Phase 02 (D1 schema + sync endpoint), Phase 03 (creator creates campaigns to track).
- Scenario criticals: C2 (D1 sync silent failure), H2 (cron race condition), H7 (orphan D1 data), H8 (duplicate leads), H10 (spend acceleration), H11 (tracking broken), H12 (partial sync).
- Blocks: Phase 06 (integration testing).

## Overview
Build the monitor skill: cron-based metrics collection from Google Ads API, local SQLite
backup (source of truth), D1 sync with retry + failure alerting, anomaly detection
(CPA spike, CTR drop, pacing), LLM-powered analysis, daily Telegram report. Runs every
6 hours for sync, daily at 9am for report.

## Key Insights
- **Local SQLite is source of truth**: Hermes VPS stores all metrics locally first.
  D1 is a sync replica for dashboard queries. If D1 goes down, Hermes continues operating.
  If D1 data is corrupted, resync from local SQLite.
- **Cron schedule matters**: sync every 6h = 4x/day. Google Ads API reports have
  ~3h latency. 6h interval ensures we capture all data. Daily report at 9am catches
  yesterday's full data.
- **Anomaly detection is threshold-based, not ML**: simple rules (CPA >30% spike,
  CTR >20% drop, spend >2x daily average) are sufficient for $500/mo budget.
  **MULTI-CAMPAIGN: baselines are PER-CAMPAIGN**, not global. Each campaign compared
  against its own 7-day history. Campaigns <7 days old skip anomaly detection.
  Campaigns without conversion tracking (`has_conversion_tracking=0`) skip CPA checks
  entirely (avoids false alarms on awareness campaigns).
  LLM analyzes the detected anomaly and generates human-readable explanation.
- **Orphan handling**: campaigns deleted in Google Ads UI → monitor marks them `archived`
  in D1. Never deletes data — historical metrics preserved.
- **Sync protocol is idempotent**: `INSERT OR REPLACE` with UNIQUE(entity_type, entity_id, date).
  Re-running sync with same date range = no duplicates, no errors.

## Requirements
- **Functional**: GAQL metrics query, local SQLite backup, D1 sync, anomaly detection,
  LLM analysis, Telegram daily report, budget tracking.
- **Non-functional**: <200 lines per Python file, retry 3x with exponential backoff,
  alert after 3 consecutive sync failures, cron via Hermes scheduler.

## Architecture
```
skills/research/google-ads/
├── SKILL.md                            # updated with monitor commands
├── scripts/
│   ├── research.py                     # Phase 01
│   ├── creator.py                      # Phase 03
│   ├── monitor.py                      # orchestrator: query → store → sync → analyze → alert
│   ├── sync_to_d1.py                  # D1 sync with retry + failure tracking
│   └── daily_report.py                # Telegram daily report generator
├── data/
│   ├── campaigns-local.db              # SQLite: source of truth for all metrics
│   ├── ad-copy-learning.db             # Phase 03
│   ├── anomaly-alerts.log              # append-only anomaly log
│   └── sync-status.json                # last sync state (for dashboard reference)
└── references/
    ├── keyword-methodology.md          # Phase 01
    └── restricted-terms.md             # Phase 03
```

Data flow:
```
Cron (every 6h):
  monitor.py
    → query Google Ads API via GAQL (impressions, clicks, cost, conversions)
    → store in local SQLite (campaigns-local.db)
    → detect anomalies (CPA spike, CTR drop, pacing)
    → if anomaly: LLM analyzes → Telegram alert immediately
    → sync_to_d1.py: POST /api/sync to Cloudflare Workers
    → on sync failure: retry 3x, log to sync-status.json
    → on 3 consecutive failures: critical alert to Telegram

Cron (daily 9am):
  daily_report.py
    → read yesterday's metrics from local SQLite
    → calculate KPIs: impressions, clicks, CTR, CPC, conversions, CPL, spend
    → identify top/bottom performers (campaigns, keywords)
    → LLM generates optimization suggestions
    → format as Telegram message (markdown)
    → send via Hermes Telegram gateway
```

## Related Code Files
- **Create**: `skills/research/google-ads/scripts/monitor.py`
- **Create**: `skills/research/google-ads/scripts/sync_to_d1.py`
- **Create**: `skills/research/google-ads/scripts/daily_report.py`
- **Update**: `skills/research/google-ads/SKILL.md` (add monitor commands)
- **Read**: `google-ads.env` (API credentials)
- **Read**: `data/campaigns-local.db` (local SQLite, source of truth)
- **Read**: Phase 02 Workers API endpoint: `POST /api/sync`

## Interfaces

### Consumes
- Google Ads API via GAQL queries (impressions, clicks, cost, conversions)
- `google-ads.env` (OAuth credentials)
- `campaigns-local.db` (read/write — source of truth)
- Hermes cron scheduler (trigger every 6h + daily 9am)
- Hermes Telegram gateway (for alerts + reports)

### Produces
- `campaigns-local.db` rows (metrics, leads, campaign status)
- POST /api/sync payload to D1 (metrics, leads, campaigns, keywords)
- Telegram alerts (anomaly detection, sync failures)
- Telegram daily report (KPIs, top/bottom performers, suggestions)
- `sync-status.json` (last sync state)
- `anomaly-alerts.log` (append-only anomaly history)

## Implementation Steps

### Step 1: Local SQLite Schema (30 min)

```python
# campaigns-local.db schema (created by monitor.py on first run)

SCHEMA = """
-- Campaigns (mirror of Google Ads + local metadata)
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    campaign_type TEXT NOT NULL DEFAULT 'search',
    daily_budget REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Daily Metrics (source of truth — synced to D1)
CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    date TEXT NOT NULL,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0.0,
    conversions INTEGER NOT NULL DEFAULT 0,
    conversion_value REAL NOT NULL DEFAULT 0.0,
    synced_to_d1 INTEGER NOT NULL DEFAULT 0,
    UNIQUE(entity_type, entity_id, date)
);

-- Anomaly Log (append-only)
CREATE TABLE IF NOT EXISTS anomaly_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL DEFAULT (datetime('now')),
    anomaly_type TEXT NOT NULL,
    entity_id TEXT,
    entity_name TEXT,
    metric_name TEXT NOT NULL,
    current_value REAL,
    baseline_value REAL,
    change_pct REAL,
    llm_analysis TEXT,
    alert_sent INTEGER NOT NULL DEFAULT 0
);
"""
```

### Step 2: Create monitor.py — Orchestrator (2h)

```python
# scripts/monitor.py
import sqlite3, json, time, pathlib
from datetime import datetime, timedelta

DB_PATH = "data/campaigns-local.db"
SYNC_URL = "https://ads-copilot-api.<subdomain>.workers.dev/api/sync"
MAX_SYNC_RETRIES = 3
BACKOFF_BASE = 5  # seconds
CONSECUTIVE_FAILURE_ALERT = 3

def main(mode="sync"):
    """Main entry point. Modes: sync, report, detect."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    if mode == "sync":
        run_sync(db)
    elif mode == "report":
        generate_daily_report(db)
    elif mode == "detect":
        detect_anomalies(db)
    elif mode == "full":
        run_sync(db)
        detect_anomalies(db)

def run_sync(db):
    """Full sync cycle: query API → store locally → sync to D1."""
    client = get_client()

    # 1. Get active campaigns from API
    campaigns = query_campaigns(client)
    for c in campaigns:
        upsert_campaign(db, c)

    # 2. Detect orphans (campaigns in API but not local, or vice versa)
    reconcile_campaigns(db, campaigns)

    # 3. Query metrics for last 7 days (catch any gaps)
    metrics = query_metrics(client, days=7)
    for m in metrics:
        upsert_metric(db, m)

    # 4. Query leads (conversion data)
    leads = query_leads(client, days=7)
    for lead in leads:
        upsert_lead(db, lead)

    db.commit()

    # 5. Sync to D1
    sync_success = sync_to_d1(db, metrics, leads, campaigns)

    # 6. Update sync status
    update_sync_status(sync_success)

    # 7. Check for consecutive failures
    if get_consecutive_failures() >= CONSECUTIVE_FAILURE_ALERT:
        send_telegram_alert("D1 sync failed 3 consecutive times. Manual check required.")

def query_metrics(client, days=7):
    """Query Google Ads API for campaign-level metrics via GAQL."""
    date_range = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    query = f"""
    SELECT
      campaign.id,
      campaign.name,
      campaign.status,
      segments.date,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM campaign
    WHERE segments.date >= '{date_range}'
    ORDER BY segments.date DESC, campaign.id
    """

    ga_service = client.get_service("GoogleAdsService")
    results = ga_service.search(query)

    metrics = []
    for row in results:
        metrics.append({
            "entity_type": "campaign",
            "entity_id": str(row.campaign.id),
            "date": str(row.segments.date),
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost": row.metrics.cost_micros / 1_000_000,  # micros to dollars
            "conversions": row.metrics.conversions,
            "conversion_value": row.metrics.conversions_value / 1_000_000,
        })

    return metrics

def detect_anomalies(db):
    """Threshold-based anomaly detection + LLM analysis.
    MULTI-CAMPAIGN: per-campaign baselines. Skip new campaigns <7 days old.
    Skip CPA checks for campaigns without conversion tracking.
    """
    anomalies = []

    # Get active campaigns with age info
    active_campaigns = db.execute("""
        SELECT c.campaign_id, c.name, c.objective, c.has_conversion_tracking,
          c.daily_budget,
          MIN(m.date) as first_metric_date,
          julianday(date('now')) - julianday(MIN(m.date)) as age_days
        FROM campaigns c
        LEFT JOIN daily_metrics m ON c.campaign_id = m.entity_id AND m.entity_type = 'campaign'
        WHERE c.status = 'active'
        GROUP BY c.campaign_id
    """).fetchall()

    for camp in active_campaigns:
        # Skip campaigns < 7 days old (no baseline)
        if camp["age_days"] is None or camp["age_days"] < 7:
            continue

        # Rule 1: CPA spike >30% (only for campaigns WITH conversion tracking)
        if camp["has_conversion_tracking"]:
            anomalies.extend(check_cpa_spike(db, camp, threshold=0.30))

        # Rule 2: CTR drop >20% (all campaigns)
        anomalies.extend(check_ctr_drop(db, camp, threshold=0.20))

        # Rule 3: Spend pacing >2x daily budget (per-campaign daily_budget)
        anomalies.extend(check_spend_pacing(db, camp, multiplier=2.0))

    # Rule 4: Possible tracking issue (all active campaigns with conversion tracking)
    anomalies.extend(check_tracking_issue(db, days=7))

    for a in anomalies:
        # LLM analyzes anomaly context
        a["llm_analysis"] = llm_analyze_anomaly(a, get_campaign_context(db, a["entity_id"]))
        save_anomaly(db, a)
        send_telegram_alert(format_anomaly_alert(a))

def check_cpa_spike(db, campaign, threshold=0.30):
    """MULTI-CAMPAIGN: per-campaign CPA baseline. Compare yesterday vs 7-day avg."""
    sql = """
    SELECT entity_id,
      SUM(cost) / NULLIF(SUM(conversions), 0) as cpa_today,
      (SELECT SUM(cost) / NULLIF(SUM(conversions), 0)
       FROM daily_metrics
       WHERE entity_type = 'campaign' AND date >= date('now', '-8 days') AND date < date('now', '-1 days')
         AND entity_id = m.entity_id) as cpa_avg_7d
    FROM daily_metrics m
    WHERE entity_type = 'campaign' AND date = date('now', '-1 days')
      AND entity_id = ? AND conversions > 0
    """
    results = db.execute(sql).fetchall()
    anomalies = []
    for r in results:
        if r["cpa_avg_7d"] and r["cpa_avg_7d"] > 0:
            change = (r["cpa_today"] - r["cpa_avg_7d"]) / r["cpa_avg_7d"]
            if change > threshold:
                anomalies.append({
                    "anomaly_type": "cpa_spike",
                    "entity_id": r["entity_id"],
                    "metric_name": "CPA",
                    "current_value": r["cpa_today"],
                    "baseline_value": r["cpa_avg_7d"],
                    "change_pct": round(change * 100, 1),
                })
    return anomalies
```

### Step 3: Create sync_to_d1.py (1.5h)

```python
# scripts/sync_to_d1.py
import json, time, requests

SYNC_URL = "https://ads-copilot-api.<subdomain>.workers.dev/api/sync"
MAX_RETRIES = 3
BACKOFF_BASE = 5

def sync_to_d1(db, metrics, leads, campaigns):
    """Push unsynced local data to D1 via POST /api/sync."""
    unsynced_metrics = get_unsynced_metrics(db)
    unsynced_leads = get_unsynced_leads(db)

    if not unsynced_metrics and not unsynced_leads:
        return True  # nothing to sync

    payload = {
        "metrics": unsynced_metrics,
        "leads": unsynced_leads,
        "campaigns": [{"campaign_id": c["id"], "name": c["name"],
                       "status": c["status"], "daily_budget": c["daily_budget"]}
                      for c in campaigns],
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                SYNC_URL,
                json=payload,
                headers={"X-Hermes-Secret": HERMES_SYNC_SECRET},
                timeout=30,
            )
            resp.raise_for_status()

            # Mark as synced
            mark_synced(db, unsynced_metrics, unsynced_leads)
            return True

        except requests.exceptions.RequestException as e:
            wait = BACKOFF_BASE ** (attempt + 1)
            log_sync_failure(f"Attempt {attempt+1}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)

    return False  # all retries exhausted
```

### Step 4: Create daily_report.py (1.5h)

```python
# scripts/daily_report.py

def generate_daily_report(db):
    """Generate daily Telegram report with KPIs, performers, suggestions."""
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    last_30 = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")

    # KPIs
    kpis = get_kpis(db, yesterday)
    # kpis = { impressions, clicks, ctr, cost, cpc, conversions, cpl, conv_rate }

    # Top performers
    top_campaigns = get_top_campaigns(db, last_30, limit=3)
    bottom_campaigns = get_bottom_campaigns(db, last_30, limit=3)
    top_keywords = get_top_keywords(db, last_30, limit=5)

    # Budget tracking
    budget = get_budget_status(db)

    # LLM optimization suggestions
    context = {
        "kpis": kpis,
        "top_campaigns": top_campaigns,
        "bottom_campaigns": bottom_campaigns,
        "budget": budget,
    }
    suggestions = llm_generate_suggestions(context)

    # Format Telegram message
    message = format_telegram_report(
        date=yesterday,
        kpis=kpis,
        top=top_campaigns,
        bottom=bottom_campaigns,
        keywords=top_keywords,
        budget=budget,
        suggestions=suggestions,
    )

    send_telegram_message(message)

def format_telegram_report(**kwargs):
    """MULTI-CAMPAIGN: per-campaign breakdown, not just top/bottom ranking.
    Each campaign shown individually with its own metrics (avoids apples-vs-oranges).
    """
    lines = [f"📊 *Google Ads Daily Report — {kwargs['date']}*"]

    # Account summary (totals)
    kpis = kwargs['kpis']
    budget = kwargs['budget']
    lines.append(f"\n*💰 Account Overview*")
    lines.append(f"Spend: ${budget['spent']:.2f} / ${budget['total']:.2f} ({budget['pacing_pct']:.0f}% paced)")
    lines.append(f"Total Clicks: {kpis['clicks']:,} | Total Leads: {kpis['conversions']}")

    # Per-campaign breakdown (primary view)
    lines.append(f"\n*🔍 Campaigns*")
    for camp in kwargs['per_campaign']:  # sorted by campaign_id, not by metric
        status_emoji = "✅" if camp['pacing_status'] == 'on_track' else ("⚠️" if camp['pacing_status'] == 'over' else "📊")
        lines.append(f"{status_emoji} *{camp['name']}* ({camp['objective']})")
        if camp['has_conversion_tracking']:
            lines.append(f"   Clicks: {camp['clicks']:,} | CTR: {camp['ctr']:.1f}% | Leads: {camp['conversions']} | CPL: ${camp['cpl']:.2f}")
        else:
            lines.append(f"   Impressions: {camp['impressions']:,} | Clicks: {camp['clicks']:,} | CTR: {camp['ctr']:.1f}% | Spend: ${camp['cost']:.2f}")
        lines.append(f"   Budget: ${camp['cost']:.2f}/${camp['daily_budget']:.2f} daily ({camp['pacing_pct']:.0f}%)")

    # Top keywords across all campaigns
    lines.append(f"\n*🔑 Top 5 Keywords (All Campaigns)*")
    lines.append(format_keyword_list(kwargs['keywords']))

    # Per-campaign LLM suggestions
    lines.append(f"\n*💡 Suggestions*")
    for camp_name, suggestion in kwargs['per_campaign_suggestions'].items():
        lines.append(f"• *{camp_name}*: {suggestion}")

    return "\n".join(lines)
```

### Step 5: Cron Setup (30 min)

Add to Hermes cron scheduler:
```
# Every 6 hours: sync metrics + anomaly detection
0 */6 * * * cd ~/hermes-agent && python3 scripts/monitor.py full

# Daily at 9am: daily report
0 9 * * * cd ~/hermes-agent && python3 scripts/daily_report.py
```

### Step 6: Orphan Handling (30 min)

```python
def reconcile_campaigns(db, api_campaigns):
    """Handle campaigns that exist locally but not in API (or vice versa)."""
    api_ids = {c["campaign_id"] for c in api_campaigns}
    local_ids = {r["campaign_id"] for r in db.execute("SELECT campaign_id FROM campaigns").fetchall()}

    # In API but not local → new campaign (sync_to_d1 handles)
    new_ids = api_ids - local_ids

    # In local but not in API → orphan (deleted externally)
    orphan_ids = local_ids - api_ids
    for oid in orphan_ids:
        db.execute("UPDATE campaigns SET status = 'archived', last_seen_at = datetime('now') WHERE campaign_id = ?", (oid,))

    # In API but status changed
    for c in api_campaigns:
        local = db.execute("SELECT status FROM campaigns WHERE campaign_id = ?", (c["campaign_id"],)).fetchone()
        if local and local["status"] != c["status"]:
            db.execute("UPDATE campaigns SET status = ?, last_seen_at = datetime('now') WHERE campaign_id = ?",
                       (c["status"], c["campaign_id"]))
```

## Todo
- [ ] Update SKILL.md with monitor commands + cron schedule
- [ ] Create local SQLite schema in monitor.py
- [ ] Implement `query_campaigns()` — GAQL query for active campaigns
- [ ] Implement `query_metrics()` — GAQL query for impressions/clicks/cost/conversions
- [ ] Implement `query_leads()` — GAQL query for conversion data
- [ ] Implement local SQLite upsert (metrics, leads, campaigns)
- [ ] Create `scripts/sync_to_d1.py` — POST /api/sync with retry (3x exponential backoff)
- [ ] Implement sync failure tracking + alert (3 consecutive failures)
- [ ] Implement anomaly detection: per-campaign CPA spike >30%, CTR drop >20%, spend pacing >2x daily_budget
- [ ] Skip anomaly detection for campaigns < 7 days old (no baseline)
- [ ] Skip CPA checks for campaigns without conversion tracking (avoids false alarms)
- [ ] Implement tracking issue detection (clicks > 0, conversions = 0 for 7+ days)
- [ ] Implement LLM analysis for detected anomalies
- [ ] Create `scripts/daily_report.py` — KPIs + top/bottom + suggestions
- [ ] Implement Telegram message formatting
- [ ] Implement budget tracking (daily spend vs pacing vs forecast)
- [ ] Implement orphan handling (campaigns deleted externally)
- [ ] Set up Hermes cron (every 6h sync, daily 9am report)
- [ ] Test: run sync manually, verify local SQLite populated
- [ ] Test: run sync, verify D1 has matching data
- [ ] Test: simulate sync failure, verify retry + alert

## Success Criteria
- Cron triggers `monitor.py full` every 6 hours without error
- Google Ads API queried via GAQL → metrics stored in local SQLite
- Unsynced data pushed to D1 via POST /api/sync (verified by querying D1)
- Sync failure: retry 3x with 5s, 25s, 125s backoff → alert after 3 consecutive failures
- Anomaly detection: per-campaign CPA spike >30% → Telegram alert with LLM analysis
- Anomaly detection: per-campaign CTR drop >20% → Telegram alert
- Anomaly detection: campaigns <7 days old skip all checks
- Anomaly detection: campaigns without conversion tracking skip CPA checks
- Daily report at 9am: per-campaign breakdown (not top/bottom ranking), pacing, suggestions per campaign
- Orphan campaigns marked `archived` (not deleted) in D1
- `synced_to_d1` flag prevents re-syncing same data

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| D1 sync silent failure → data loss (C2) | Crit | Local SQLite = source of truth. D1 = replica. Alert after 3 consecutive failures. Manual resync tool. |
| Cron race condition (H2) | High | SQLite WAL mode + UNIQUE constraints. Idempotent upsert. Single sync at a time. |
| Orphan data in D1 (H7) | Med | Mark `archived`, not delete. Historical metrics preserved. Dashboard filters by status. |
| Duplicate leads (H8) | Med | UNIQUE(source, conversion_id) in both local SQLite and D1. |
| Spend acceleration (H10) | High | Anomaly detection: spend >2x daily average → immediate alert. No auto-action. |
| Tracking broken (H11) | High | Detect: clicks >0, conversions =0 for 7+ days → "Possible tracking issue" alert. |
| Partial sync (H12) | Med | Atomic sync per entity type. `synced_to_d1` flag per row. Next cron picks up unsynced. |
| GAQL query returns stale data | Low | Google Ads has ~3h latency. 6h sync interval > latency. |

## Security
- OAuth credentials from google-ads.env (gitignored)
- D1 sync uses X-Hermes-Secret header
- Telegram alerts via existing Hermes gateway (no new credentials)
- Local SQLite on VPS (not publicly accessible)

## Next Steps
- Phase 05 (dashboard) — reads synced D1 data for visualization
- Phase 06 (integration testing) — end-to-end: create → sync → dashboard → report
