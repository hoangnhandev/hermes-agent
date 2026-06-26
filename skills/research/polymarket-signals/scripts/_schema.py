#!/usr/bin/env python3
"""SQLite schema + table creation for polymarket-signals skill.

Called once by init_db(). Tables and indexes are defined here;
CRUD lives in store.py.
"""

SCHEMA_VERSION = 1

DDL_TABLES = """
CREATE TABLE IF NOT EXISTS markets(
    condition_id TEXT PRIMARY KEY,
    slug TEXT, question TEXT, category TEXT,
    category_override TEXT,
    category_confidence REAL DEFAULT 1.0,
    clob_token_ids TEXT, outcome_prices TEXT,
    volume_usd REAL, end_date TEXT,
    source_first_seen TEXT
);
CREATE TABLE IF NOT EXISTS predictions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT, scan_id INTEGER,
    status TEXT DEFAULT 'pending',
    predicted_p REAL, market_p REAL, confidence REAL,
    sources TEXT, rationale TEXT, category TEXT,
    scan_ts TEXT, ensemble_breakdown TEXT,
    UNIQUE(condition_id, scan_id),
    FOREIGN KEY(condition_id) REFERENCES markets(condition_id),
    FOREIGN KEY(scan_id) REFERENCES scans(id)
);
CREATE TABLE IF NOT EXISTS outcomes(
    condition_id TEXT PRIMARY KEY,
    outcome_int INTEGER,
    resolved_ts TEXT, resolution_source TEXT,
    outcome_confidence REAL DEFAULT 1.0,
    outcome_raw TEXT, resolution_status TEXT,
    previous_outcome_int INTEGER
);
CREATE TABLE IF NOT EXISTS scans(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, n_markets INTEGER DEFAULT 0,
    categories TEXT, cost_note TEXT,
    status TEXT DEFAULT 'running'
);
CREATE TABLE IF NOT EXISTS schema_meta(
    key TEXT PRIMARY KEY, value TEXT
);
"""

DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_pred_category ON predictions(category);
CREATE INDEX IF NOT EXISTS idx_pred_cid ON predictions(condition_id);
CREATE INDEX IF NOT EXISTS idx_pred_scan_ts ON predictions(scan_ts);
CREATE INDEX IF NOT EXISTS idx_pred_scan_id ON predictions(scan_id);
CREATE INDEX IF NOT EXISTS idx_markets_category ON markets(category);
"""

DDL_SEED = """
INSERT OR IGNORE INTO schema_meta(key, value) VALUES(?, ?);
"""

# Future migrations: list of (to_version, sql)
MIGRATIONS: list[tuple[int, str]] = []
