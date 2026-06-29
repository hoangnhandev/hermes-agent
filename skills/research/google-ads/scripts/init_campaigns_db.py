#!/usr/bin/env python3
"""
Initialize campaigns-local.db with updated schema for monitoring.
This adds monitoring-specific tables to the existing _store.py schema.
"""

import sqlite3
from pathlib import Path
from datetime import datetime


def init_campaigns_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the campaigns database with monitoring schema.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        SQLite connection object
    """
    print(f"[DB] Initializing campaigns database: {db_path}")

    # Create database directory if it doesn't exist
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries

    # Create all tables including monitoring schema
    create_campaigns_tables(conn)

    print("[DB] Campaigns database initialized successfully")
    return conn


def create_campaigns_tables(conn: sqlite3.Connection):
    """Create database tables for campaigns monitoring."""
    print("[DB] Creating campaigns database tables")

    cursor = conn.cursor()

    # Campaigns table (extended from existing)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT NOT NULL UNIQUE,
            niche TEXT NOT NULL,
            location TEXT NOT NULL,
            monthly_budget REAL NOT NULL,
            daily_budget REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            objective TEXT DEFAULT 'leads',
            has_conversion_tracking INTEGER DEFAULT 1,
            last_seen_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')

    # Daily Metrics table (source of truth)
    cursor.execute('''
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
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(entity_type, entity_id, date)
        )
    ''')

    # Anomaly Log table (append-only)
    cursor.execute('''
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
        )
    ''')

    # Ad copy history table (from existing)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_copy_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT NOT NULL,
            headlines TEXT NOT NULL,
            descriptions TEXT NOT NULL,
            path1 TEXT,
            path2 TEXT,
            approval_status TEXT NOT NULL,
            policy_violations TEXT,
            performance_data TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
        )
    ''')

    # Keywords table (from existing)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            search_volume_estimate TEXT,
            competition TEXT,
            intent TEXT,
            suggested_bid_cpc REAL,
            match_type TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
        )
    ''')

    # Create indexes for better query performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_campaigns_id ON campaigns(campaign_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_metrics_entity_date ON daily_metrics(entity_type, entity_id, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_metrics_sync_status ON daily_metrics(synced_to_d1)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_log_type ON anomaly_log(anomaly_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_log_detected_at ON anomaly_log(detected_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_copy_history_campaign_id ON ad_copy_history(campaign_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_keywords_campaign_id ON keywords(campaign_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_copy_history_status ON ad_copy_history(approval_status)')

    conn.commit()
    print("[DB] Campaigns tables created successfully")


def upsert_metric(conn: sqlite3.Connection, entity_type: str, entity_id: str, date: str,
                  impressions: int = 0, clicks: int = 0, cost: float = 0.0,
                  conversions: int = 0, conversion_value: float = 0.0) -> int:
    """Upsert daily metric record.

    Args:
        conn: SQLite connection
        entity_type: Type of entity (e.g., 'campaign', 'ad_group')
        entity_id: Entity ID
        date: Date string (YYYY-MM-DD)
        impressions: Number of impressions
        clicks: Number of clicks
        cost: Cost in currency
        conversions: Number of conversions
        conversion_value: Total conversion value

    Returns:
        Row ID of inserted/updated record
    """
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO daily_metrics (
            entity_type, entity_id, date, impressions, clicks, cost, conversions, conversion_value, synced_to_d1
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
    ''', (entity_type, entity_id, date, impressions, clicks, cost, conversions, conversion_value))

    conn.commit()
    return cursor.lastrowid


def get_unsynced_metrics(conn: sqlite3.Connection) -> list:
    """Get metrics that haven't been synced to D1.

    Args:
        conn: SQLite connection

    Returns:
        List of unsynced metric records
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM daily_metrics
        WHERE synced_to_d1 = 0
        ORDER BY date, entity_type, entity_id
    ''')

    return [dict(row) for row in cursor.fetchall()]


def mark_metrics_synced(conn: sqlite3.Connection, metric_ids: list):
    """Mark metrics as synced to D1.

    Args:
        conn: SQLite connection
        metric_ids: List of metric IDs to mark as synced
    """
    if not metric_ids:
        return

    cursor = conn.cursor()
    placeholders = ','.join(['?' for _ in metric_ids])
    cursor.execute(f'''
        UPDATE daily_metrics
        SET synced_to_d1 = 1
        WHERE id IN ({placeholders})
    ''', metric_ids)

    conn.commit()
    print(f"[DB] Marked {len(metric_ids)} metrics as synced to D1")


def save_anomaly(conn: sqlite3.Connection, anomaly_type: str, entity_id: str, entity_name: str,
                metric_name: str, current_value: float, baseline_value: float,
                change_pct: float, llm_analysis: str = None) -> int:
    """Save anomaly detection result.

    Args:
        conn: SQLite connection
        anomaly_type: Type of anomaly
        entity_id: Entity ID
        entity_name: Entity name
        metric_name: Metric name
        current_value: Current value
        baseline_value: Baseline value
        change_pct: Percentage change
        llm_analysis: LLM analysis (optional)

    Returns:
        Row ID of inserted anomaly record
    """
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO anomaly_log (
            anomaly_type, entity_id, entity_name, metric_name,
            current_value, baseline_value, change_pct, llm_analysis
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (anomaly_type, entity_id, entity_name, metric_name,
          current_value, baseline_value, change_pct, llm_analysis))

    conn.commit()
    return cursor.lastrowid


def get_campaign_baseline_metrics(conn: sqlite3.Connection, campaign_id: str, days: int = 30) -> dict:
    """Get baseline metrics for a campaign over specified days.

    Args:
        conn: SQLite connection
        campaign_id: Campaign ID
        days: Number of days to calculate baseline

    Returns:
        Dictionary with baseline metrics
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            AVG(impressions) as avg_impressions,
            AVG(clicks) as avg_clicks,
            AVG(cost) as avg_cost,
            AVG(conversions) as avg_conversions,
            AVG(conversion_value) as avg_conversion_value,
            COUNT(*) as days_with_data
        FROM daily_metrics
        WHERE entity_type = 'campaign'
          AND entity_id = ?
          AND date >= date('now', '-{} days')
    '''.format(days), (campaign_id,))

    row = cursor.fetchone()
    if row and row['days_with_data'] > 0:
        return {
            'avg_impressions': row['avg_impressions'] or 0,
            'avg_clicks': row['avg_clicks'] or 0,
            'avg_cost': row['avg_cost'] or 0.0,
            'avg_conversions': row['avg_conversions'] or 0,
            'avg_conversion_value': row['avg_conversion_value'] or 0.0,
            'days_with_data': row['days_with_data']
        }

    return {
        'avg_impressions': 0,
        'avg_clicks': 0,
        'avg_cost': 0.0,
        'avg_conversions': 0,
        'avg_conversion_value': 0.0,
        'days_with_data': 0
    }


def get_campaign_metrics_summary(conn: sqlite3.Connection, campaign_id: str, date: str) -> dict:
    """Get metrics summary for a campaign on a specific date.

    Args:
        conn: SQLite connection
        campaign_id: Campaign ID
        date: Date string (YYYY-MM-DD)

    Returns:
        Dictionary with metrics summary
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM daily_metrics
        WHERE entity_type = 'campaign'
          AND entity_id = ?
          AND date = ?
    ''', (campaign_id, date))

    row = cursor.fetchone()
    if row:
        return dict(row)

    return {
        'impressions': 0,
        'clicks': 0,
        'cost': 0.0,
        'conversions': 0,
        'conversion_value': 0.0,
        'ctr': 0.0,
        'avg_cpc': 0.0,
        'cpl': 0.0
    }


def main():
    """Test campaigns database functionality and create the actual database."""
    print("[DB] Testing campaigns database functionality")

    # Initialize test database
    test_db_path = Path("data/campaigns-local-test.db")
    if test_db_path.exists():
        test_db_path.unlink()

    conn = init_campaigns_db(test_db_path)

    # Test upserting metrics
    metric_id = upsert_metric(
        conn, 'campaign', 'test-campaign-001', '2026-06-29',
        impressions=1000, clicks=50, cost=25.0, conversions=5, conversion_value=125.0
    )
    print(f"[DB] Test metric upserted with ID: {metric_id}")

    # Test getting unsynced metrics
    unsynced = get_unsynced_metrics(conn)
    print(f"[DB] Found {len(unsynced)} unsynced metrics")

    # Test saving anomaly
    anomaly_id = save_anomaly(
        conn, 'CPA_SPIKE', 'test-campaign-001', 'Test Campaign',
        'cost_per_lead', 15.0, 10.0, 50.0, 'CPA increased by 50%'
    )
    print(f"[DB] Test anomaly saved with ID: {anomaly_id}")

    # Test getting baseline metrics
    baseline = get_campaign_baseline_metrics(conn, 'test-campaign-001', 30)
    print(f"[DB] Baseline metrics: {baseline}")

    # Clean up
    conn.close()
    test_db_path.unlink()
    print("[DB] Campaigns test completed and cleaned up")

    # Create the actual campaigns-local.db
    print("[DB] Creating actual campaigns-local.db")
    actual_db_path = Path("data/campaigns-local.db")
    conn_actual = init_campaigns_db(actual_db_path)
    conn_actual.close()
    print(f"[DB] Created actual database at: {actual_db_path}")


if __name__ == "__main__":
    main()