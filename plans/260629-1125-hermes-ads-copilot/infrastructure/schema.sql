-- All money columns below are in VND (the skill's display currency). Source
-- amounts sync from the local SQLite store (also VND). The Google Ads API
-- path converts VND → micros via ACCOUNT_CURRENCY (see _budget_calc.py).
-- Campaigns (with multi-campaign support)
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    campaign_type TEXT NOT NULL DEFAULT 'search',
    daily_budget REAL NOT NULL,            -- VND
    monthly_budget REAL NOT NULL DEFAULT 0.0,  -- VND (per-campaign; 0 when unknown)
    objective TEXT NOT NULL DEFAULT 'leads',
    has_conversion_tracking INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT
);

-- Ad Groups
CREATE TABLE IF NOT EXISTS ad_groups (
    ad_group_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    cpc_bid REAL,                          -- VND
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

-- Ads
CREATE TABLE IF NOT EXISTS ads (
    ad_id TEXT PRIMARY KEY,
    ad_group_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    headline_1 TEXT,
    headline_2 TEXT,
    headline_3 TEXT,
    description_1 TEXT,
    description_2 TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    approval_status TEXT NOT NULL DEFAULT 'approved',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (ad_group_id) REFERENCES ad_groups(ad_group_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

-- Keywords
CREATE TABLE IF NOT EXISTS keywords (
    keyword_id TEXT PRIMARY KEY,
    ad_group_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    text TEXT NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'PHRASE',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (ad_group_id) REFERENCES ad_groups(ad_group_id)
);

-- Daily Metrics (synced from Hermes)
CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    date TEXT NOT NULL,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0.0,           -- VND
    conversions INTEGER NOT NULL DEFAULT 0,
    conversion_value REAL NOT NULL DEFAULT 0.0,  -- VND
    synced_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_type, entity_id, date)
);

-- Leads
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    conversion_id TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'google_ads',
    conversion_date TEXT NOT NULL,
    conversion_value REAL DEFAULT 0.0,       -- VND
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, campaign_id, conversion_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

-- Ad Copy History (learning store)
CREATE TABLE IF NOT EXISTS ad_copy_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    headline TEXT NOT NULL,
    description TEXT NOT NULL,
    approval_status TEXT NOT NULL,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    conversions INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

-- Optimization Log
CREATE TABLE IF NOT EXISTS optimization_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    action TEXT NOT NULL,
    metric_before REAL,
    metric_after REAL,
    suggestion TEXT,
    status TEXT NOT NULL DEFAULT 'suggested',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

-- API Keys (for sync authentication)
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

-- Anomalies (synced from Hermes anomaly_log; wire 5). One row per detection;
-- deduped by (detected_at, entity_id, anomaly_type). detected_at carries the
-- local detection timestamp; metric values are in the metric's native unit
-- (CPA/CTR are ratios, cost-derived CPA is VND).
CREATE TABLE IF NOT EXISTS anomalies (
    detected_at TEXT NOT NULL,
    anomaly_type TEXT NOT NULL,
    entity_id TEXT,
    entity_name TEXT,
    metric_name TEXT NOT NULL,
    current_value REAL,
    baseline_value REAL,
    change_pct REAL,
    synced_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (detected_at, entity_id, anomaly_type)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_metrics_entity_date ON daily_metrics(entity_type, entity_id, date);
CREATE INDEX IF NOT EXISTS idx_metrics_date ON daily_metrics(date);
CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id);
CREATE INDEX IF NOT EXISTS idx_leads_date ON leads(conversion_date);
CREATE INDEX IF NOT EXISTS idx_keywords_campaign ON keywords(campaign_id);
CREATE INDEX IF NOT EXISTS idx_ad_groups_campaign ON ad_groups(campaign_id);
CREATE INDEX IF NOT EXISTS idx_ads_campaign ON ads(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_anomalies_detected ON anomalies(detected_at);