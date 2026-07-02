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

from _store import (
    init_campaigns_db,
    upsert_metric,
    save_anomaly,
    get_campaign_baseline_metrics,
    has_conversion_tracking,
    find_or_create_keyword,
    mark_anomalies_alerted,
)
from _env import load_google_ads_env
from _budget_calc import from_micros
from _dates import account_local_today

# Map Google Ads CampaignStatus enum → our DB status string. The API returns
# an enum (ENABLED/PAUSED/REMOVED); we store readable values so the dashboard
# shows clear status badges. ENABLED=active (serving), PAUSED, REMOVED.
_CAMPAIGN_STATUS_MAP = {"ENABLED": "active", "PAUSED": "paused", "REMOVED": "removed"}


def _map_campaign_status(api_status: Any) -> str:
    """Normalize a Google Ads CampaignStatus enum/value to a DB status string."""
    raw = getattr(api_status, "name", str(api_status))  # proto-plus enum → name
    return _CAMPAIGN_STATUS_MAP.get(raw.split(".")[-1].strip().upper(), "active")


class GoogleAdsMonitor:
    """Main monitor class for Google Ads monitoring."""

    def __init__(self, db_path: Path):
        """Initialize monitor with database path."""
        self.db_path = db_path
        self.conn = init_campaigns_db(db_path)
        self.sync_status_path = db_path.parent / "sync-status.json"

        # Populate os.environ from google-ads.env BEFORE reading any value.
        # Fixes M3: customer_id was read before load_google_ads_env() ran, so
        # under cron (empty shell env, no vars exported) it was always "" →
        # INVALID_CUSTOMER_ID on every GAQL query. load_from_env (below) reads
        # post-load so the client itself worked, but self.customer_id didn't.
        try:
            load_google_ads_env()
        except Exception as e:
            print(f"[Monitor] ⚠️ load_google_ads_env failed: {e}")

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
            # v21: Campaign has no daily_budget_micros field (budget lives on the
            # campaign_budget resource). Select campaign_budget.amount_micros (a
            # linked resource, selectable from a campaign query) and read it from
            # row.campaign_budget below; falls back to 0 if unset.
            gaql_query = """
            SELECT
              campaign.id,
              campaign.name,
              campaign.status,
              campaign.advertising_channel_type,
              campaign.bidding_strategy_type,
              campaign.start_date,
              campaign.end_date,
              campaign_budget.amount_micros
            FROM campaign
            WHERE campaign.status != 'REMOVED'
            ORDER BY campaign.name
            """

            query_response = self.googleads_client.get_service("GoogleAdsService").search(
                customer_id=self.customer_id,
                query=gaql_query
            )

            campaigns = []
            for row in query_response:
                campaign = row.campaign
                # v21: budget lives on the linked campaign_budget resource (not
                # on Campaign). Read amount_micros from the row's budget field.
                budget_micros = getattr(getattr(row, "campaign_budget", None),
                                        "amount_micros", 0) or 0
                campaigns.append({
                    "campaign_id": str(campaign.id),
                    "name": campaign.name,
                    "status": _map_campaign_status(campaign.status),
                    "channel_type": campaign.advertising_channel_type,
                    "bidding_strategy": campaign.bidding_strategy_type,
                    "daily_budget_micros": budget_micros,
                    "daily_budget": from_micros(budget_micros) if budget_micros else 0.0,
                    "start_date": campaign.start_date,
                    "end_date": campaign.end_date
                })

            print(f"[Monitor] Found {len(campaigns)} active campaigns from API")
            return campaigns

        except GoogleAdsException as e:
            # Re-raise so run_sync() can mark the cycle FAILED. Previously this
            # returned [] — indistinguishable from a legitimately-empty account,
            # so an expired token / dead query silently looked like "0 campaigns".
            print(f"[Monitor] Google Ads API error: {e}")
            raise
        except Exception as e:
            print(f"[Monitor] Error getting campaigns from API: {e}")
            raise

    def query_metrics(self, days: int = 7) -> List[Dict[str, Any]]:
        """Query campaign metrics from Google Ads API."""
        if not self.googleads_client:
            print("[Monitor] Google Ads client not available, returning empty metrics")
            return []

        try:
            today = datetime.now(timezone.utc)
            date_range = (today - timedelta(days=days)).strftime("%Y-%m-%d")
            today_str = today.strftime("%Y-%m-%d")

            gaql_query = f"""
            SELECT
              campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
              segments.date,
              metrics.impressions, metrics.clicks, metrics.cost_micros,
              metrics.conversions, metrics.conversions_value
            FROM campaign
            WHERE segments.date >= '{date_range}' AND segments.date <= '{today_str}'
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
                    "status": _map_campaign_status(campaign.status),
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


    def query_keyword_metrics(self, days: int = 7) -> List[Dict[str, Any]]:
        """Query keyword-level metrics from Google Ads API (plan wire 2).

        Mirrors query_metrics but against `keyword_view`, returning one row per
        (campaign, ad_group, keyword text, match_type, date). Cost is converted
        to VND via from_micros. run_sync maps each row to a keywords.id and
        upserts it into daily_metrics with entity_type='keyword' so the optimize
        + reporting paths have keyword-level data.
        """
        if not self.googleads_client:
            print("[Monitor] Google Ads client not available, returning empty keyword metrics")
            return []

        try:
            today = datetime.now(timezone.utc)
            date_range = (today - timedelta(days=days)).strftime("%Y-%m-%d")
            today_str = today.strftime("%Y-%m-%d")

            gaql_query = f"""
            SELECT
              segments.date,
              campaign.id, campaign.status,
              ad_group.id,
              ad_group_criterion.keyword.text,
              ad_group_criterion.keyword.match_type,
              ad_group_criterion.status,
              metrics.impressions, metrics.clicks, metrics.cost_micros,
              metrics.conversions, metrics.conversions_value
            FROM keyword_view
            WHERE segments.date >= '{date_range}' AND segments.date <= '{today_str}'
              AND campaign.status = 'ENABLED'
              AND ad_group_criterion.status = 'ENABLED'
            ORDER BY segments.date DESC, campaign.id
            """

            query_response = self.googleads_client.get_service("GoogleAdsService").search(
                customer_id=self.customer_id,
                query=gaql_query
            )

            rows = []
            for row in query_response:
                metrics_row = row.metrics
                kw = row.ad_group_criterion.keyword
                # API match_type is an enum (e.g. KeywordMatchType.PHRASE) → lowercase.
                match_type = kw.match_type.name.lower() if kw.match_type else "phrase"
                rows.append({
                    "campaign_id": str(row.campaign.id),
                    "ad_group_id": str(row.ad_group.id),
                    "keyword_text": kw.text or "",
                    "match_type": match_type,
                    "date": row.segments.date,
                    "impressions": metrics_row.impressions,
                    "clicks": metrics_row.clicks,
                    "cost": from_micros(metrics_row.cost_micros) if metrics_row.cost_micros else 0.0,
                    "conversions": metrics_row.conversions,
                    "conversion_value": metrics_row.conversions_value,
                })

            print(f"[Monitor] Queried {len(rows)} keyword metrics from API")
            return rows

        except GoogleAdsException as e:
            print(f"[Monitor] Google Ads API error querying keyword metrics: {e}")
            return []
        except Exception as e:
            print(f"[Monitor] Error querying keyword metrics: {e}")
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

        # Get all existing campaign IDs from database (active + paused; archived excluded)
        cursor.execute("SELECT campaign_id FROM campaigns WHERE status != 'archived'")
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

        # Upsert API campaigns. ON CONFLICT preserves staged metadata (niche,
        # objective, created_at) and refreshes volatile fields + the REAL status
        # (was hardcoded 'active' → paused campaigns showed as active).
        for campaign in api_campaigns:
            cursor.execute('''
                INSERT INTO campaigns (
                    campaign_id, niche, location, monthly_budget, daily_budget,
                    status, last_seen_at, has_conversion_tracking
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_id) DO UPDATE SET
                    niche=excluded.niche,
                    status=excluded.status,
                    daily_budget=excluded.daily_budget,
                    monthly_budget=excluded.monthly_budget,
                    last_seen_at=excluded.last_seen_at,
                    updated_at=datetime('now'),
                    has_conversion_tracking=excluded.has_conversion_tracking
            ''', (
                campaign['campaign_id'],
                campaign.get('name', '') or campaign.get('niche', ''),
                '',
                campaign.get('monthly_budget') or (campaign.get('daily_budget', 0) * 30),
                campaign.get('daily_budget', 0),
                campaign.get('status', 'active'),
                datetime.now().isoformat(),
                has_conversion_tracking()
            ))

        self.conn.commit()
        print(f"[Monitor] Reconciled {len(api_campaigns)} campaigns")

    def _already_alerted(self, entity_id: str, anomaly_type: str) -> bool:
        """True if (entity, type) was already alerted today — dedupe for wire 4.

        Prevents re-pinging Telegram on every sync for the same-day anomaly.
        Cross-day persistence re-alerts (intended: still anomalous next day).
        """
        try:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT 1 FROM anomaly_log WHERE entity_id=? AND anomaly_type=? "
                "AND alert_sent=1 AND date(detected_at)=date('now') LIMIT 1",
                (entity_id, anomaly_type),
            )
            return cur.fetchone() is not None
        except Exception as e:
            print(f"[Monitor] _already_alerted check error: {e}")
            return False

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

            # Get today's metrics. "today" is ACCOUNT-LOCAL (wire 6c) to match
            # segments.date (account-local, VN=UTC+7); a naive UTC datetime.now()
            # drifts the day boundary and misses/phantoms the day-edge row.
            today = account_local_today()
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

        # Save anomalies, dedupe by (entity+type+day), ping Telegram (wire 4).
        # Telegram is optional + best-effort: a missing dep or outage must never
        # block the sync cycle.
        try:
            from telegram_notify import send_anomaly
        except Exception as e:
            send_anomaly = None
            print(f"[Monitor] telegram_notify unavailable ({e}); anomalies log only")

        alerted_ids = []
        for anomaly in anomalies_found:
            if self._already_alerted(anomaly['campaign_id'], anomaly['type']):
                continue
            aid = save_anomaly(
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
            if aid == -1:
                continue
            if send_anomaly:
                try:
                    sent = send_anomaly(
                        anomaly['type'],
                        anomaly.get('niche') or anomaly['campaign_id'],
                        anomaly['metric'],
                        anomaly['current_value'],
                        anomaly['baseline_value'],
                        anomaly['change_pct'],
                    )
                except Exception as e:
                    print(f"[Monitor] Telegram anomaly send error: {e}")
                    sent = False
                if sent:
                    alerted_ids.append(aid)

        if alerted_ids:
            mark_anomalies_alerted(self.conn, alerted_ids)

        print(f"[Monitor] Detected {len(anomalies_found)} anomalies, "
              f"{len(alerted_ids)} alerted via Telegram")

    def run_sync(self) -> bool:
        """Run full sync cycle."""
        print("[Monitor] Starting full sync cycle")

        try:
            # Get active campaigns from API. An empty list here means the query
            # SUCCEEDED and the account has 0 campaigns (not an error). Real API
            # failures now raise from get_active_campaigns_from_api → caught by
            # the except below → marked failed.
            api_campaigns = self.get_active_campaigns_from_api()
            if not api_campaigns:
                print("[Monitor] No active campaigns (query OK) — nothing to sync")
                status = self.load_sync_status()
                status['last_sync_at'] = datetime.now().isoformat()
                status['last_sync_status'] = 'success'
                status['consecutive_failures'] = 0
                status['metrics_synced'] = 0
                status['leads_synced'] = 0
                self.save_sync_status(status)
                return True

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

            # Keyword-level metrics → daily_metrics entity_type='keyword' (wire 2).
            # Map each GAQL keyword_view row to a keywords.id (insert if the keyword
            # is new to this campaign) so optimize + reporting have keyword data.
            keyword_metrics = self.query_keyword_metrics(7)
            for km in keyword_metrics:
                if not km["keyword_text"]:
                    continue
                kw_id = find_or_create_keyword(
                    self.conn, km["campaign_id"], km["keyword_text"], km["match_type"]
                )
                if kw_id == -1:
                    continue
                upsert_metric(
                    self.conn,
                    'keyword',
                    str(kw_id),
                    km['date'],
                    km['impressions'],
                    km['clicks'],
                    km['cost'],
                    km['conversions'],
                    km['conversion_value'],
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