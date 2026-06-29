#!/usr/bin/env python3
"""
Sync Google Ads metrics from local SQLite to Cloudflare D1 with retry logic.
"""

import argparse
import sqlite3
import json
import requests
import time
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


class D1Sync:
    """Handle syncing metrics from local SQLite to Cloudflare D1."""

    def __init__(self, db_path: Path):
        """Initialize D1 sync with database path."""
        self.db_path = db_path
        self.sync_url = os.getenv("WORKERS_API_URL", "https://ads-copilot-api.subdomain.workers.dev/api/sync")
        self.hermes_secret = os.getenv("HERMES_SYNC_SECRET")
        self.max_retries = 3
        self.backoff_base = 5

        if not self.hermes_secret:
            print("[D1 Sync] WARNING: HERMES_SYNC_SECRET not set")

        # Connect to database
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def get_unsynced_metrics(self) -> List[Dict[str, Any]]:
        """Get metrics that haven't been synced to D1."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM daily_metrics
            WHERE synced_to_d1 = 0
            ORDER BY date, entity_type, entity_id
        ''')

        return [dict(row) for row in cursor.fetchall()]

    def get_unsynced_anomalies(self) -> List[Dict[str, Any]]:
        """Get anomalies that haven't been synced to D1."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM anomaly_log
            WHERE alert_sent = 0
            ORDER BY detected_at
        ''')

        return [dict(row) for row in cursor.fetchall()]

    def get_unsynced_campaigns(self) -> List[Dict[str, Any]]:
        """Get campaigns that haven't been synced to D1."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM campaigns
            WHERE status = 'active'
            ORDER BY updated_at DESC
        ''')

        return [dict(row) for row in cursor.fetchall()]

    def build_sync_payload(self, metrics: List[Dict[str, Any]],
                          anomalies: List[Dict[str, Any]],
                          campaigns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build payload for D1 sync API."""
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "anomalies": anomalies,
            "campaigns": campaigns,
            "sync_type": "full"
        }

    def sync_to_d1(self, payload: Dict[str, Any]) -> bool:
        """Sync payload to D1 with retry logic."""
        if not self.hermes_secret:
            print("[D1 Sync] No HERMES_SYNC_SECRET set, skipping sync")
            return False

        headers = {
            "Content-Type": "application/json",
            "X-Hermes-Secret": self.hermes_secret,
            "User-Agent": "Hermes-GoogleAds-Monitor/1.0"
        }

        for attempt in range(self.max_retries):
            try:
                print(f"[D1 Sync] Attempt {attempt + 1} of {self.max_retries}")

                response = requests.post(
                    self.sync_url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )

                if response.status_code == 200:
                    response_data = response.json()
                    if response_data.get("success", False):
                        print(f"[D1 Sync] Sync successful: {response_data}")
                        return True
                    else:
                        print(f"[D1 Sync] Sync failed: {response_data.get('error', 'Unknown error')}")
                else:
                    print(f"[D1 Sync] HTTP error {response.status_code}: {response.text}")

            except requests.exceptions.Timeout:
                print(f"[D1 Sync] Timeout on attempt {attempt + 1}")
            except requests.exceptions.ConnectionError:
                print(f"[D1 Sync] Connection error on attempt {attempt + 1}")
            except requests.exceptions.RequestException as e:
                print(f"[D1 Sync] Request error on attempt {attempt + 1}: {e}")
            except Exception as e:
                print(f"[D1 Sync] Unexpected error on attempt {attempt + 1}: {e}")

            # Wait with exponential backoff
            if attempt < self.max_retries - 1:
                wait_time = self.backoff_base ** (attempt + 1)
                print(f"[D1 Sync] Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)

        print(f"[D1 Sync] Failed after {self.max_retries} attempts")
        return False

    def mark_synced(self, metric_ids: List[int], anomaly_ids: List[int]):
        """Mark metrics and anomalies as synced to D1."""
        cursor = self.conn.cursor()

        # Mark metrics as synced
        if metric_ids:
            placeholders = ','.join(['?' for _ in metric_ids])
            cursor.execute(f'''
                UPDATE daily_metrics
                SET synced_to_d1 = 1
                WHERE id IN ({placeholders})
            ''', metric_ids)
            print(f"[D1 Sync] Marked {len(metric_ids)} metrics as synced")

        # Mark anomalies as alerted (synced)
        if anomaly_ids:
            placeholders = ','.join(['?' for _ in anomaly_ids])
            cursor.execute(f'''
                UPDATE anomaly_log
                SET alert_sent = 1
                WHERE id IN ({placeholders})
            ''', anomaly_ids)
            print(f"[D1 Sync] Marked {len(anomaly_ids)} anomalies as alerted")

        self.conn.commit()

    def log_sync_failure(self, error_message: str):
        """Log sync failure to sync-status.json."""
        sync_status_path = self.db_path.parent / "sync-status.json"

        if sync_status_path.exists():
            with open(sync_status_path, 'r') as f:
                status = json.load(f)
        else:
            status = {
                "last_sync_at": None,
                "last_sync_status": "never_run",
                "consecutive_failures": 0,
                "metrics_synced": 0,
                "leads_synced": 0
            }

        status["last_sync_status"] = "failed"
        status["last_sync_at"] = datetime.now().isoformat()
        status["consecutive_failures"] = status.get("consecutive_failures", 0) + 1

        with open(sync_status_path, 'w') as f:
            json.dump(status, f, indent=2)

        print(f"[D1 Sync] Sync failure logged: {error_message}")

    def run_sync(self) -> bool:
        """Run the complete sync process."""
        print("[D1 Sync] Starting sync process")

        try:
            # Get unsynced data
            metrics = self.get_unsynced_metrics()
            anomalies = self.get_unsynced_anomalies()
            campaigns = self.get_unsynced_campaigns()

            if not metrics and not anomalies and not campaigns:
                print("[D1 Sync] No unsynced data found")
                return True

            print(f"[D1 Sync] Found {len(metrics)} metrics, {len(anomalies)} anomalies, {len(campaigns)} campaigns to sync")

            # Build payload
            payload = self.build_sync_payload(metrics, anomalies, campaigns)

            # Sync to D1
            success = self.sync_to_d1(payload)

            if success:
                # Mark as synced
                metric_ids = [m['id'] for m in metrics if 'id' in m]
                anomaly_ids = [a['id'] for a in anomalies if 'id' in a]
                self.mark_synced(metric_ids, anomaly_ids)

                print(f"[D1 Sync] Sync completed successfully")
                return True
            else:
                self.log_sync_failure("D1 sync failed after retries")
                return False

        except Exception as e:
            error_msg = f"Sync error: {str(e)}"
            print(f"[D1 Sync] {error_msg}")
            self.log_sync_failure(error_msg)
            return False

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print("[D1 Sync] Database connection closed")


def main():
    """Main entry point for standalone sync."""
    parser = argparse.ArgumentParser(description='Sync Google Ads data to D1')
    parser.add_argument('--db-path', type=Path,
                       default=Path('data/campaigns-local.db'),
                       help='Database path')

    args = parser.parse_args()

    # Initialize sync
    d1_sync = D1Sync(args.db_path)

    try:
        success = d1_sync.run_sync()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[D1 Sync] Fatal error: {e}")
        sys.exit(1)
    finally:
        d1_sync.close()


if __name__ == "__main__":
    main()