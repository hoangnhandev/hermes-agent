#!/usr/bin/env python3
import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the ad copy learning database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        SQLite connection object
    """
    print(f"[DB] Initializing database: {db_path}")

    # Create database directory if it doesn't exist
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries

    # Create tables
    create_tables(conn)

    print("[DB] Database initialized successfully")
    return conn


def create_tables(conn: sqlite3.Connection):
    """Create database tables for ad copy learning and monitoring."""
    print("[DB] Creating database tables")

    cursor = conn.cursor()

    # Campaigns table (updated with monitoring fields)
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
            has_conversion_tracking INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Ad copy history table
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

    # Keywords table
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

    # Performance metrics table (renamed to daily_metrics)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            date TEXT NOT NULL,
            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0,
            conversions INTEGER DEFAULT 0,
            conversion_value REAL DEFAULT 0.0,
            synced_to_d1 INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(entity_type, entity_id, date)
        )
    ''')

    # Anomaly Log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS anomaly_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_at TEXT DEFAULT (datetime('now')),
            anomaly_type TEXT NOT NULL,
            entity_id TEXT,
            entity_name TEXT,
            metric_name TEXT NOT NULL,
            current_value REAL,
            baseline_value REAL,
            change_pct REAL,
            llm_analysis TEXT,
            alert_sent INTEGER DEFAULT 0
        )
    ''')

    # Create indexes for better query performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_campaigns_id ON campaigns(campaign_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_copy_history_campaign_id ON ad_copy_history(campaign_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_keywords_campaign_id ON keywords(campaign_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_metrics_composite ON daily_metrics(entity_type, entity_id, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_metrics_sync ON daily_metrics(synced_to_d1)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_log_detected ON anomaly_log(detected_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_log_type ON anomaly_log(anomaly_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_log_alert ON anomaly_log(alert_sent)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_copy_history_status ON ad_copy_history(approval_status)')

    conn.commit()
    print("[DB] Tables created successfully")


def save_campaign(conn: sqlite3.Connection, campaign_data: Dict[str, Any]) -> str:
    """Save campaign data to database.

    Args:
        conn: SQLite connection
        campaign_data: Campaign information

    Returns:
        Campaign ID
    """
    campaign_id = campaign_data.get("campaign_id", f"campaign-{datetime.now().strftime('%Y%m%d-%H%M%S')}")

    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO campaigns (
            campaign_id, niche, location, monthly_budget, daily_budget, status
        ) VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        campaign_id,
        campaign_data.get("niche", ""),
        campaign_data.get("location", ""),
        campaign_data.get("monthly_budget", 0.0),
        campaign_data.get("daily_budget", 0.0),
        campaign_data.get("status", "active")
    ))

    conn.commit()
    print(f"[DB] Saved campaign: {campaign_id}")
    return campaign_id


def save_copy(conn: sqlite3.Connection, campaign_id: str, copy_data: List[Dict[str, Any]], approval_status: str, policy_violations: List[str]):
    """Save ad copy data to database.

    Args:
        conn: SQLite connection
        campaign_id: Campaign ID
        copy_data: List of ad copy variations
        approval_status: 'approved' or 'rejected'
        policy_violations: List of policy violation messages
    """
    cursor = conn.cursor()

    for copy in copy_data:
        cursor.execute('''
            INSERT INTO ad_copy_history (
                campaign_id, headlines, descriptions, path1, path2, approval_status, policy_violations
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            campaign_id,
            json.dumps(copy.get("headlines", [])),
            json.dumps(copy.get("descriptions", [])),
            copy.get("path1", ""),
            copy.get("path2", ""),
            approval_status,
            json.dumps(policy_violations) if policy_violations else json.dumps([])
        ))

    conn.commit()
    print(f"[DB] Saved {len(copy_data)} copy variations for campaign {campaign_id} with status: {approval_status}")


def save_keywords(conn: sqlite3.Connection, campaign_id: str, keywords: List[Dict[str, Any]]):
    """Save keyword data to database.

    Args:
        conn: SQLite connection
        campaign_id: Campaign ID
        keywords: List of keyword data
    """
    cursor = conn.cursor()

    for keyword in keywords:
        cursor.execute('''
            INSERT INTO keywords (
                campaign_id, keyword, search_volume_estimate, competition, intent, suggested_bid_cpc, match_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            campaign_id,
            keyword.get("keyword", ""),
            keyword.get("search_volume_estimate", ""),
            keyword.get("competition", ""),
            keyword.get("intent", ""),
            keyword.get("suggested_bid_cpc", 0.0),
            keyword.get("match_type", "phrase")
        ))

    conn.commit()
    print(f"[DB] Saved {len(keywords)} keywords for campaign {campaign_id}")


def get_total_existing_daily_budget(conn: sqlite3.Connection) -> float:
    """Get total daily budget from all active campaigns.

    Args:
        conn: SQLite connection

    Returns:
        Total daily budget
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(daily_budget) FROM campaigns WHERE status = 'active'
    ''')
    result = cursor.fetchone()
    total = result[0] if result[0] else 0.0

    print(f"[DB] Total existing daily budget: ${total}")
    return total


def get_total_monthly_budget(conn: sqlite3.Connection) -> float:
    """Get total monthly budget from all active campaigns.

    Args:
        conn: SQLite connection

    Returns:
        Total monthly budget
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(monthly_budget) FROM campaigns WHERE status = 'active'
    ''')
    result = cursor.fetchone()
    total = result[0] if result[0] else 0.0

    print(f"[DB] Total existing monthly budget: ${total}")
    return total


def get_top_performing_copy(conn: sqlite3.Connection, limit: int = 5) -> List[Dict[str, Any]]:
    """Get top performing ad copy variations.

    Args:
        conn: SQLite connection
        limit: Maximum number of results to return

    Returns:
        List of top performing ad copy data
    """
    # For now, return most recently approved copy
    # In future, this would use performance metrics to rank

    cursor = conn.cursor()
    cursor.execute('''
        SELECT h.*, c.niche, c.location
        FROM ad_copy_history h
        JOIN campaigns c ON h.campaign_id = c.campaign_id
        WHERE h.approval_status = 'approved'
        ORDER BY h.created_at DESC
        LIMIT ?
    ''', (limit,))

    results = []
    for row in cursor.fetchall():
        copy_data = {
            "campaign_id": row["campaign_id"],
            "niche": row["niche"],
            "location": row["location"],
            "headlines": json.loads(row["headlines"]),
            "descriptions": json.loads(row["descriptions"]),
            "path1": row["path1"],
            "path2": row["path2"],
            "created_at": row["created_at"]
        }
        results.append(copy_data)

    print(f"[DB] Found {len(results)} top performing copy variations")
    return results


def get_campaign_summary(conn: sqlite3.Connection, campaign_id: str) -> Optional[Dict[str, Any]]:
    """Get campaign summary including copy and keywords.

    Args:
        conn: SQLite connection
        campaign_id: Campaign ID

    Returns:
        Campaign summary data or None if not found
    """
    cursor = conn.cursor()

    # Get campaign details
    cursor.execute('''
        SELECT * FROM campaigns WHERE campaign_id = ?
    ''', (campaign_id,))
    campaign = cursor.fetchone()

    if not campaign:
        print(f"[DB] Campaign not found: {campaign_id}")
        return None

    # Get ad copy history
    cursor.execute('''
        SELECT * FROM ad_copy_history WHERE campaign_id = ? ORDER BY created_at
    ''', (campaign_id,))
    copy_history = [dict(row) for row in cursor.fetchall()]

    # Get keywords
    cursor.execute('''
        SELECT * FROM keywords WHERE campaign_id = ?
    ''', (campaign_id,))
    keywords = [dict(row) for row in cursor.fetchall()]

    summary = {
        "campaign": dict(campaign),
        "copy_history": copy_history,
        "keywords": keywords,
        "total_copy": len(copy_history),
        "total_keywords": len(keywords)
    }

    print(f"[DB] Retrieved campaign summary for {campaign_id}")
    return summary


def export_learning_data(conn: sqlite3.Connection, output_path: Path):
    """Export learning data for analysis or model training.

    Args:
        conn: SQLite connection
        output_path: Path to save export file
    """
    cursor = conn.cursor()

    # Get all approved copy with performance context
    cursor.execute('''
        SELECT
            h.headlines,
            h.descriptions,
            h.path1,
            h.path2,
            h.created_at,
            c.niche,
            c.location,
            c.monthly_budget
        FROM ad_copy_history h
        JOIN campaigns c ON h.campaign_id = c.campaign_id
        WHERE h.approval_status = 'approved'
        ORDER BY h.created_at DESC
    ''')

    export_data = []
    for row in cursor.fetchall():
        export_data.append({
            "headlines": json.loads(row["headlines"]),
            "descriptions": json.loads(row["descriptions"]),
            "path1": row["path1"],
            "path2": row["path2"],
            "created_at": row["created_at"],
            "niche": row["niche"],
            "location": row["location"],
            "monthly_budget": row["monthly_budget"]
        })

    with open(output_path, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"[DB] Exported {len(export_data)} learning records to {output_path}")


def upsert_metric(conn: sqlite3.Connection, entity_type: str, entity_id: str, date: str,
                   impressions: int = 0, clicks: int = 0, cost: float = 0.0,
                   conversions: int = 0, conversion_value: float = 0.0) -> bool:
    """Upsert daily metric record.

    Args:
        conn: SQLite connection
        entity_type: Type of entity ('campaign', 'keyword', etc.)
        entity_id: Entity ID
        date: Date in YYYY-MM-DD format
        impressions: Number of impressions
        clicks: Number of clicks
        cost: Cost in local currency
        conversions: Number of conversions
        conversion_value: Conversion value

    Returns:
        True if successful, False otherwise
    """
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO daily_metrics (
                entity_type, entity_id, date, impressions, clicks, cost,
                conversions, conversion_value, synced_to_d1
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        ''', (entity_type, entity_id, date, impressions, clicks, cost, conversions, conversion_value))

        conn.commit()
        print(f"[DB] Upserted metric: {entity_type} {entity_id} on {date}")
        return True

    except Exception as e:
        print(f"[DB] Error upserting metric: {e}")
        return False


def get_unsynced_metrics(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Get daily metrics that haven't been synced to D1 yet.

    Returns:
        List of unsynced metric records
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT entity_type, entity_id, date, impressions, clicks, cost,
               conversions, conversion_value
        FROM daily_metrics
        WHERE synced_to_d1 = 0
        ORDER BY date, entity_type, entity_id
    ''')

    metrics = []
    for row in cursor.fetchall():
        metrics.append(dict(row))

    print(f"[DB] Found {len(metrics)} unsynced metrics")
    return metrics


def mark_metrics_synced(conn: sqlite3.Connection, entity_ids: List[str], date: str = None):
    """Mark metrics as synced to D1.

    Args:
        conn: SQLite connection
        entity_ids: List of entity IDs to mark as synced
        date: Optional date filter
    """
    if not entity_ids:
        return

    cursor = conn.cursor()

    if date:
        placeholders = ','.join(['?' for _ in entity_ids])
        cursor.execute(f'''
            UPDATE daily_metrics
            SET synced_to_d1 = 1
            WHERE entity_id IN ({placeholders}) AND date = ?
        ''', entity_ids + [date])
    else:
        placeholders = ','.join(['?' for _ in entity_ids])
        cursor.execute(f'''
            UPDATE daily_metrics
            SET synced_to_d1 = 1
            WHERE entity_id IN ({placeholders})
        ''', entity_ids)

    conn.commit()
    print(f"[DB] Marked {len(entity_ids)} metrics as synced")


def save_anomaly(conn: sqlite3.Connection, anomaly_type: str, entity_id: str, entity_name: str,
                 metric_name: str, current_value: float, baseline_value: float, change_pct: float,
                 llm_analysis: str = None) -> int:
    """Save anomaly detection result.

    Args:
        conn: SQLite connection
        anomaly_type: Type of anomaly ('CPA_SPIKE', 'CTR_DROP', etc.)
        entity_id: Entity ID (campaign, keyword, etc.)
        entity_name: Entity name for display
        metric_name: Name of the metric with anomaly
        current_value: Current metric value
        baseline_value: Baseline metric value for comparison
        change_pct: Percentage change from baseline
        llm_analysis: Optional LLM analysis of the anomaly

    Returns:
        Anomaly ID if successful, -1 otherwise
    """
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO anomaly_log (
                anomaly_type, entity_id, entity_name, metric_name,
                current_value, baseline_value, change_pct, llm_analysis
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (anomaly_type, entity_id, entity_name, metric_name,
              current_value, baseline_value, change_pct, llm_analysis))

        conn.commit()
        anomaly_id = cursor.lastrowid
        print(f"[DB] Saved anomaly: {anomaly_type} for {entity_name} (ID: {anomaly_id})")
        return anomaly_id

    except Exception as e:
        print(f"[DB] Error saving anomaly: {e}")
        return -1


def get_unsynced_anomalies(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Get anomalies that haven't been alerted/synced yet.

    Returns:
        List of unsynced anomaly records
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, detected_at, anomaly_type, entity_id, entity_name,
               metric_name, current_value, baseline_value, change_pct
        FROM anomaly_log
        WHERE alert_sent = 0
        ORDER BY detected_at
    ''')

    anomalies = []
    for row in cursor.fetchall():
        anomalies.append(dict(row))

    print(f"[DB] Found {len(anomalies)} unsynced anomalies")
    return anomalies


def mark_anomalies_alerted(conn: sqlite3.Connection, anomaly_ids: List[int]):
    """Mark anomalies as alerted (synced).

    Args:
        conn: SQLite connection
        anomaly_ids: List of anomaly IDs to mark
    """
    if not anomaly_ids:
        return

    cursor = conn.cursor()
    placeholders = ','.join(['?' for _ in anomaly_ids])
    cursor.execute(f'''
        UPDATE anomaly_log
        SET alert_sent = 1
        WHERE id IN ({placeholders})
    ''', anomaly_ids)

    conn.commit()
    print(f"[DB] Marked {len(anomaly_ids)} anomalies as alerted")


def get_campaign_baseline_metrics(conn: sqlite3.Connection, campaign_id: str, days: int = 30) -> Dict[str, Any]:
    """Get baseline metrics for a campaign over specified period.

    Args:
        conn: SQLite connection
        campaign_id: Campaign ID
        days: Number of days to look back for baseline

    Returns:
        Dictionary with baseline metrics
    """
    cursor = conn.cursor()

    # Calculate date range
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    cursor.execute('''
        SELECT
            COUNT(*) as days_with_data,
            AVG(impressions) as avg_impressions,
            AVG(clicks) as avg_clicks,
            AVG(cost) as avg_cost,
            AVG(conversions) as avg_conversions,
            AVG(conversion_value) as avg_conversion_value
        FROM daily_metrics
        WHERE entity_type = 'campaign' AND entity_id = ?
          AND date >= ? AND date <= ?
    ''', (campaign_id, start_date.isoformat(), end_date.isoformat()))

    row = cursor.fetchone()
    if row:
        baseline = dict(row)
        # Convert None values to 0
        for key, value in baseline.items():
            if value is None:
                baseline[key] = 0.0
        print(f"[DB] Baseline for campaign {campaign_id}: {baseline['days_with_data']} days")
        return baseline

    return {
        'days_with_data': 0,
        'avg_impressions': 0.0,
        'avg_clicks': 0.0,
        'avg_cost': 0.0,
        'avg_conversions': 0.0,
        'avg_conversion_value': 0.0
    }


def init_campaigns_db(db_path: Path) -> sqlite3.Connection:
    """Initialize campaigns database (alias for init_db for compatibility).

    Args:
        db_path: Path to SQLite database file

    Returns:
        SQLite connection object
    """
    return init_db(db_path)


def main():
    """Test database functionality."""
    print("[DB] Testing database functionality")

    # Initialize test database
    test_db_path = Path("test-ad-copy-learning.db")
    if test_db_path.exists():
        test_db_path.unlink()

    conn = init_db(test_db_path)

    # Test saving campaign
    campaign_data = {
        "campaign_id": "test-campaign-001",
        "niche": "plumbing",
        "location": "Austin, TX",
        "monthly_budget": 1000,
        "daily_budget": 33.33,
        "status": "active"
    }

    campaign_id = save_campaign(conn, campaign_data)

    # Test saving copy
    copy_data = [
        {
            "headlines": ["Professional Plumbing Services", "Expert Plumbers", "Local Plumbing"],
            "descriptions": ["Professional plumbing services in Austin. Call today!", "Expert plumbers for all your needs."],
            "path1": "plumbing",
            "path2": "austin"
        }
    ]

    save_copy(conn, campaign_id, copy_data, "approved", [])

    # Test saving keywords
    keywords = [
        {"keyword": "plumbing services austin", "search_volume_estimate": "high", "competition": "medium", "intent": "transactional", "suggested_bid_cpc": 8.50, "match_type": "phrase"}
    ]

    save_keywords(conn, campaign_id, keywords)

    # Test getting summary
    summary = get_campaign_summary(conn, campaign_id)
    if summary:
        print(f"[DB] Test successful: Campaign {summary['campaign']['campaign_id']} has {summary['total_copy']} copy variations and {summary['total_keywords']} keywords")

    # Clean up
    conn.close()
    test_db_path.unlink()
    print("[DB] Test completed and cleaned up")


if __name__ == "__main__":
    main()