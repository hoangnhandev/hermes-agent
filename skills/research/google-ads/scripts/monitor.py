#!/usr/bin/env python3
"""
Hermes Google Ads Monitor - Cron orchestrator for syncing metrics and detecting anomalies.
"""

import argparse
import sqlite3
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

# Add the scripts directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    GOOGLE_ADS_AVAILABLE = True
except ImportError:
    GOOGLE_ADS_AVAILABLE = False

from _store import init_campaigns_db, upsert_metric, save_anomaly, get_campaign_baseline_metrics
from _env import load_google_ads_env
from _budget_calc import from_micros


class GoogleAdsMonitor:
    """Main monitor class for Google Ads monitoring."""

    def __init__(self, db_path: Path):
        """Initialize monitor with database path."""
        self.db_path = db_path
        self.conn = init_campaigns_db(db_path)
        self.sync_status_path = db_path.parent / "sync-status.json"

        # Customer ID to query = the child account (GOOGLE_ADS_CUSTOMER_ID env),
        # NOT login_customer_id (which is the MCC manager). Fixes M2: querying
        # login_customer_id hits the shell MCC account (no campaigns).
        self.customer_id = (os.getenv("GOOGLE_ADS_CUSTOMER_ID") or "").replace("-", "").strip()

        # Initialize Google Ads client if available. Fixes M1: use load_from_env
        # (consistent with deploy.py, reads google-ads.env via _env loader),
        # NOT load_from_storage (google-ads.yaml).
        self.googleads_client = None
        if GOOGLE_ADS_AVAILABLE:
            try:
                load_google_ads_env()  # populate os.environ from google-ads.env
                self.googleads_client = GoogleAdsClient.load_from_env(version=os.getenv("GOOGLE_ADS_API_VERSION", "v21"))
                print(f"[Monitor] Google Ads client initialized "
                      f"(customer_id={self.customer_id or 'NOT SET'})")
                if not self.customer_id:
                    print("[Monitor] ⚠️ GOOGLE_ADS_CUSTOMER_ID not set — "
                          "GAQL queries will fail. Set it in google-ads.env.")
            except Exception as e:
                print(f"[Monitor] Google Ads client initialization failed: {e}")
                self.googleads_client = None
        else:
            print("[Monitor] Google Ads library not available")

    def load_sync_status(self) -> Dict[str, Any]:
        """Load sync status from JSON file."""
        if self.sync_status_path.exists():
            with open(self.sync_status_path, 'r') as f:
                return json.load(f)
        return {
            "last_sync_at": None,
            "last_sync_status": "never_run",
            "consecutive_failures": 0,
            "metrics_synced": 0,
            "leads_synced": 0
        }

    def save_sync_status(self, status: Dict[str, Any]):
        """Save sync status to JSON file."""
        with open(self.sync_status_path, 'w') as f:
            json.dump(status, f, indent=2)
        print(f"[Monitor] Sync status saved: {status}")

    def get_active_campaigns_from_api(self) -> List[Dict[str, Any]]:
        """Get active campaigns from Google Ads API."""
        if not self.googleads_client:
            print("[Monitor] Google Ads client not available, returning empty campaigns")
            return []

        try:
            gaql_query = """
            SELECT
              campaign.id,
              campaign.name,
              campaign.status,
              campaign.advertising_channel_type,
              campaign.bidding_strategy_type,
              campaign.daily_budget_micros,
              campaign.start_date,
              campaign.end_date
            FROM campaign
            WHERE campaign.status = 'ENABLED'
            ORDER BY campaign.name
            """

            query_response = self.googleads_client.get_service("GoogleAdsService").search(
                customer_id=self.customer_id,
                query=gaql_query
            )

            campaigns = []
            for row in query_response:
                campaign = row.campaign
                campaigns.append({
                    "campaign_id": str(campaign.id),
                    "name": campaign.name,
                    "status": campaign.status,
                    "channel_type": campaign.advertising_channel_type,
                    "bidding_strategy": campaign.bidding_strategy_type,
                    "daily_budget_micros": campaign.daily_budget_micros,
                    "daily_budget": from_micros(campaign.daily_budget_micros) if campaign.daily_budget_micros else 0.0,
                    "start_date": campaign.start_date,
                    "end_date": campaign.end_date
                })

            print(f"[Monitor] Found {len(campaigns)} active campaigns from API")
            return campaigns

        except GoogleAdsException as e:
            print(f"[Monitor] Google Ads API error: {e}")
            return []
        except Exception as e:
            print(f"[Monitor] Error getting campaigns from API: {e}")
            return []

    def query_metrics(self, days: int = 7) -> List[Dict[str, Any]]:
        """Query campaign metrics from Google Ads API."""
        if not self.googleads_client:
            print("[Monitor] Google Ads client not available, returning empty metrics")
            return []

        try:
            date_range = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

            gaql_query = f"""
            SELECT
              campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
              segments.date,
              metrics.impressions, metrics.clicks, metrics.cost_micros,
              metrics.conversions, metrics.conversions_value
            FROM campaign
            WHERE segments.date >= '{date_range}'
              AND campaign.status = 'ENABLED'
            ORDER BY segments.date DESC, campaign.id
            """

            query_response = self.googleads_client.get_service("GoogleAdsService").search(
                customer_id=self.customer_id,
                query=gaql_query
            )

            metrics = []
            for row in query_response:
                segment = row.segments
                campaign = row.campaign
                metrics_row = row.metrics

                metrics.append({
                    "campaign_id": str(campaign.id),
                    "campaign_name": campaign.name,
                    "status": campaign.status,
                    "channel_type": campaign.advertising_channel_type,
                    "date": segment.date,
                    "impressions": metrics_row.impressions,
                    "clicks": metrics_row.clicks,
                    "cost_micros": metrics_row.cost_micros,
                    "cost": from_micros(metrics_row.cost_micros) if metrics_row.cost_micros else 0.0,
                    "conversions": metrics_row.conversions,
                    "conversion_value": metrics_row.conversions_value
                })

            print(f"[Monitor] Queried {len(metrics)} metrics from API")
            return metrics

        except GoogleAdsException as e:
            print(f"[Monitor] Google Ads API error querying metrics: {e}")
            return []
        except Exception as e:
            print(f"[Monitor] Error querying metrics: {e}")
            return []

    def query_leads(self, days: int = 7) -> List[Dict[str, Any]]:
        """Query conversion data from Google Ads API."""
        if not self.googleads_client:
            print("[Monitor] Google Ads client not available, returning empty leads")
            return []

        try:
            date_range = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

            gaql_query = f"""
            SELECT
              campaign.id,
              segments.conversion_action,
              segments.conversion_action_category,
              segments.conversion_action_name,
              segments.date,
              segments.conversion_value,
              metrics.conversions
            FROM conversion_action
            WHERE segments.date >= '{date_range}'
              AND metrics.conversions > 0
            ORDER BY segments.date DESC
            """

            query_response = self.googleads_client.get_service("GoogleAdsService").search(
                customer_id=self.customer_id,
                query=gaql_query
            )

            leads = []
            for row in query_response:
                segment = row.segments
                metrics_row = row.metrics

                leads.append({
                    "campaign_id": str(row.campaign.id),
                    "conversion_action": segment.conversion_action,
                    "conversion_action_category": segment.conversion_action_category,
                    "conversion_action_name": segment.conversion_action_name,
                    "date": segment.date,
                    "conversion_value": segment.conversion_value,
                    "conversions": metrics_row.conversions
                })

            print(f"[Monitor] Queried {len(leads)} leads from API")
            return leads

        except GoogleAdsException as e:
            print(f"[Monitor] Google Ads API error querying leads: {e}")
            return []
        except Exception as e:
            print(f"[Monitor] Error querying leads: {e}")
            return []

    def reconcile_campaigns(self, api_campaigns: List[Dict[str, Any]]):
        """Reconcile campaigns - mark missing ones as archived."""
        cursor = self.conn.cursor()

        # Get all existing campaign IDs from database
        cursor.execute("SELECT campaign_id FROM campaigns WHERE status = 'active'")
        db_campaigns = [row[0] for row in cursor.fetchall()]

        # Get API campaign IDs
        api_campaign_ids = [camp['campaign_id'] for camp in api_campaigns]

        # Find campaigns that exist in DB but not in API (orphans)
        orphans = set(db_campaigns) - set(api_campaign_ids)

        if orphans:
            print(f"[Monitor] Found {len(orphans)} orphan campaigns to archive")
            cursor.execute(
                "UPDATE campaigns SET status = 'archived', updated_at = ? WHERE campaign_id IN ({})".format(
                    ','.join(['?' for _ in orphans])
                ),
                [datetime.now().isoformat()] + list(orphans)
            )
            self.conn.commit()

        # Upsert API campaigns to database
        for campaign in api_campaigns:
            cursor.execute('''
                INSERT OR REPLACE INTO campaigns (
                    campaign_id, niche, location, monthly_budget, daily_budget, status, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                campaign['campaign_id'],
                campaign.get('name', ''),
                '',  # Will be updated from other sources
                campaign.get('daily_budget', 0) * 30,  # Estimate monthly from daily
                campaign.get('daily_budget', 0),
                'active',
                datetime.now().isoformat()
            ))

        self.conn.commit()
        print(f"[Monitor] Reconciled {len(api_campaigns)} campaigns")

    def detect_anomalies(self):
        """Detect anomalies based on thresholds."""
        print("[Monitor] Starting anomaly detection")

        # Get all active campaigns
        cursor = self.conn.cursor()
        cursor.execute("SELECT campaign_id, niche, objective, has_conversion_tracking FROM campaigns WHERE status = 'active'")
        campaigns = cursor.fetchall()

        anomalies_found = []

        for campaign_id, niche, objective, has_conv_tracking in campaigns:
            # Skip campaigns less than 7 days old
            baseline = get_campaign_baseline_metrics(self.conn, campaign_id, 30)
            if baseline['days_with_data'] < 7:
                continue

            # Get today's metrics
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute('''
                SELECT impressions, clicks, cost, conversions FROM daily_metrics
                WHERE entity_type = 'campaign' AND entity_id = ? AND date = ?
            ''', (campaign_id, today))

            row = cursor.fetchone()
            if not row:
                continue

            current_metrics = dict(row)

            # Check CPA spike (only for campaigns with conversion tracking)
            if has_conv_tracking and baseline['avg_conversions'] > 0:
                baseline_cpa = baseline['avg_cost'] / baseline['avg_conversions']
                current_cpa = current_metrics['cost'] / current_metrics['conversions'] if current_metrics['conversions'] > 0 else float('inf')

                if current_cpa != float('inf'):
                    cpa_change_pct = ((current_cpa - baseline_cpa) / baseline_cpa) * 100
                    if abs(cpa_change_pct) > 30:  # 30% threshold
                        anomalies_found.append({
                            'type': 'CPA_SPIKE',
                            'campaign_id': campaign_id,
                            'niche': niche,
                            'metric': 'cost_per_lead',
                            'current_value': current_cpa,
                            'baseline_value': baseline_cpa,
                            'change_pct': cpa_change_pct
                        })

            # Check CTR drop
            if baseline['avg_clicks'] > 0:
                baseline_ctr = (baseline['avg_clicks'] / baseline['avg_impressions']) * 100 if baseline['avg_impressions'] > 0 else 0
                current_ctr = (current_metrics['clicks'] / current_metrics['impressions']) * 100 if current_metrics['impressions'] > 0 else 0

                if current_ctr < baseline_ctr:
                    ctr_change_pct = ((current_ctr - baseline_ctr) / baseline_ctr) * 100
                    if ctr_change_pct < -20:  # 20% drop threshold
                        anomalies_found.append({
                            'type': 'CTR_DROP',
                            'campaign_id': campaign_id,
                            'niche': niche,
                            'metric': 'click_through_rate',
                            'current_value': current_ctr,
                            'baseline_value': baseline_ctr,
                            'change_pct': ctr_change_pct
                        })

            # Check for tracking issues (clicks > 0, conversions = 0)
            if (current_metrics['clicks'] > 0 and current_metrics['conversions'] == 0 and
                has_conv_tracking and baseline['avg_conversions'] > 0):
                anomalies_found.append({
                    'type': 'TRACKING_ISSUE',
                    'campaign_id': campaign_id,
                    'niche': niche,
                    'metric': 'conversion_tracking',
                    'current_value': 0,
                    'baseline_value': baseline['avg_conversions'],
                    'change_pct': -100
                })

        # Save anomalies to database
        for anomaly in anomalies_found:
            save_anomaly(
                self.conn,
                anomaly['type'],
                anomaly['campaign_id'],
                anomaly['niche'],
                anomaly['metric'],
                anomaly['current_value'],
                anomaly['baseline_value'],
                anomaly['change_pct']
                # TODO: LLM analysis - will be implemented later
            )

        print(f"[Monitor] Detected {len(anomalies_found)} anomalies")

        # TODO: Send Telegram alerts for anomalies
        if anomalies_found:
            print("[Monitor] Anomalies detected - Telegram alerts would be sent here")

    def run_sync(self) -> bool:
        """Run full sync cycle."""
        print("[Monitor] Starting full sync cycle")

        try:
            # Get active campaigns from API
            api_campaigns = self.get_active_campaigns_from_api()
            if not api_campaigns:
                print("[Monitor] No campaigns found or API error")
                return False

            # Reconcile campaigns
            self.reconcile_campaigns(api_campaigns)

            # Query metrics for last 7 days
            metrics = self.query_metrics(7)
            metrics_synced = 0

            for metric in metrics:
                upsert_metric(
                    self.conn,
                    'campaign',
                    metric['campaign_id'],
                    metric['date'],
                    metric['impressions'],
                    metric['clicks'],
                    metric['cost'],
                    metric['conversions'],
                    metric['conversion_value']
                )
                metrics_synced += 1

            # Query leads (conversion data)
            leads = self.query_leads(7)
            leads_synced = len(leads)

            # Call sync_to_d1.py to push unsynced data
            if (Path(__file__).parent / "sync_to_d1.py").exists():
                try:
                    import subprocess
                    result = subprocess.run(
                        [sys.executable, str(Path(__file__).parent / "sync_to_d1.py")],
                        capture_output=True,
                        text=True
                    )
                    print(f"[Monitor] D1 sync result: {result.returncode}")
                    if result.stdout:
                        print(f"[Monitor] D1 sync stdout: {result.stdout}")
                except Exception as e:
                    print(f"[Monitor] Error running sync_to_d1.py: {e}")

            # Update sync status
            status = self.load_sync_status()
            status['last_sync_at'] = datetime.now().isoformat()
            status['last_sync_status'] = 'success'
            status['consecutive_failures'] = 0
            status['metrics_synced'] = metrics_synced
            status['leads_synced'] = leads_synced
            self.save_sync_status(status)

            print(f"[Monitor] Sync completed successfully: {metrics_synced} metrics, {leads_synced} leads")
            return True

        except Exception as e:
            print(f"[Monitor] Sync failed: {e}")

            # Update sync status with failure
            status = self.load_sync_status()
            status['last_sync_at'] = datetime.now().isoformat()
            status['last_sync_status'] = 'failed'
            status['consecutive_failures'] += 1
            self.save_sync_status(status)

            # Alert if 3+ consecutive failures
            if status['consecutive_failures'] >= 3:
                print("[Monitor] ALERT: 3 consecutive sync failures!")
                # TODO: Send Telegram alert

            return False

    def generate_daily_report(self):
        """Generate daily report (placeholder - calls daily_report.py)."""
        print("[Monitor] Generating daily report")

        if (Path(__file__).parent / "daily_report.py").exists():
            try:
                import subprocess
                result = subprocess.run(
                    [sys.executable, str(Path(__file__).parent / "daily_report.py")],
                    capture_output=True,
                    text=True
                )
                print(f"[Monitor] Daily report result: {result.returncode}")
                if result.stdout:
                    print(f"[Monitor] Daily report stdout: {result.stdout}")
            except Exception as e:
                print(f"[Monitor] Error running daily_report.py: {e}")
        else:
            print("[Monitor] daily_report.py not found")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print("[Monitor] Database connection closed")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Google Ads Monitor')
    parser.add_argument('--mode', choices=['sync', 'report', 'detect', 'full'],
                       default='full', help='Operation mode')
    parser.add_argument('--db-path', type=Path,
                       default=Path('data/campaigns-local.db'),
                       help='Database path')

    args = parser.parse_args()

    # Initialize monitor
    monitor = GoogleAdsMonitor(args.db_path)

    try:
        if args.mode in ['sync', 'full']:
            success = monitor.run_sync()
            if not success:
                sys.exit(1)

        if args.mode == 'full':
            monitor.detect_anomalies()

        if args.mode in ['report', 'full']:
            monitor.generate_daily_report()

        if args.mode == 'detect':
            monitor.detect_anomalies()

    except Exception as e:
        print(f"[Monitor] Error: {e}")
        sys.exit(1)
    finally:
        monitor.close()


if __name__ == "__main__":
    main()