#!/usr/bin/env python3
"""
Generate daily Google Ads report for Telegram with per-campaign breakdown.
"""

import sqlite3
import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from _env import load_google_ads_env  # self-contained under cron
from _budget_calc import fmt_vnd


class DailyReportGenerator:
    """Generate daily reports for Telegram."""

    def __init__(self, db_path: Path):
        """Initialize report generator with database path."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        # Telegram settings
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def get_per_campaign_kpis(self, date: str) -> List[Dict[str, Any]]:
        """Get KPIs for each campaign on a specific date."""
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT
                c.campaign_id,
                c.niche,
                c.objective,
                c.daily_budget,
                c.monthly_budget,
                dm.impressions,
                dm.clicks,
                dm.cost,
                dm.conversions,
                dm.conversion_value,
                CASE WHEN dm.clicks > 0 THEN (dm.clicks * 100.0 / dm.impressions) ELSE 0 END as ctr,
                CASE WHEN dm.clicks > 0 THEN (dm.cost / dm.clicks) ELSE 0 END as avg_cpc,
                CASE WHEN dm.conversions > 0 THEN (dm.cost / dm.conversions) ELSE NULL END as cpl
            FROM campaigns c
            LEFT JOIN daily_metrics dm ON c.campaign_id = dm.entity_id
                AND dm.entity_type = 'campaign'
                AND dm.date = ?
            WHERE c.status = 'active'
            ORDER BY c.niche, c.campaign_id
        ''', (date,))

        campaigns = []
        for row in cursor.fetchall():
            campaign_data = dict(row)

            # Calculate pacing
            if campaign_data['daily_budget'] > 0:
                pacing_pct = (campaign_data['cost'] / campaign_data['daily_budget']) * 100
                campaign_data['pacing_pct'] = min(100, pacing_pct)
            else:
                campaign_data['pacing_pct'] = 0

            campaigns.append(campaign_data)

        return campaigns

    def get_top_keywords(self, date: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top keywords by conversions for the date."""
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT
                k.keyword,
                k.match_type,
                dm.impressions,
                dm.clicks,
                dm.cost,
                dm.conversions,
                CASE WHEN dm.clicks > 0 THEN (dm.cost / dm.clicks) ELSE 0 END as avg_cpc
            FROM keywords k
            JOIN daily_metrics dm ON k.keyword = dm.entity_id
                AND dm.entity_type = 'keyword'
                AND dm.date = ?
            WHERE dm.conversions > 0
            ORDER BY dm.conversions DESC, dm.clicks DESC
            LIMIT ?
        ''', (date, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_account_summary(self, date: str) -> Dict[str, Any]:
        """Get account-level summary for the date."""
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT
                COUNT(*) as active_campaigns,
                SUM(impressions) as total_impressions,
                SUM(clicks) as total_clicks,
                SUM(cost) as total_cost,
                SUM(conversions) as total_conversions,
                SUM(conversion_value) as total_conversion_value,
                CASE WHEN SUM(clicks) > 0 THEN (SUM(clicks) * 100.0 / SUM(impressions)) ELSE 0 END as overall_ctr,
                CASE WHEN SUM(clicks) > 0 THEN (SUM(cost) / SUM(clicks)) ELSE 0 END as overall_avg_cpc,
                CASE WHEN SUM(conversions) > 0 THEN (SUM(cost) / SUM(conversions)) ELSE NULL END as overall_cpl
            FROM daily_metrics
            WHERE entity_type = 'campaign'
              AND date = ?
        ''', (date,))

        row = cursor.fetchone()
        if row:
            summary = dict(row)
            # Handle NULL values
            for key, value in summary.items():
                if value is None:
                    summary[key] = 0
            return summary

        return {
            'active_campaigns': 0,
            'total_impressions': 0,
            'total_clicks': 0,
            'total_cost': 0,
            'total_conversions': 0,
            'total_conversion_value': 0,
            'overall_ctr': 0,
            'overall_avg_cpc': 0,
            'overall_cpl': None
        }

    def llm_generate_suggestions(self, context: Dict[str, Any]) -> str:
        """Generate LLM suggestions for campaign optimization.

        TODO: This will be implemented with Hermes LLM integration.
        For now, returns placeholder suggestions.
        """
        # Placeholder implementation
        suggestions = []

        if context.get('low_ctr_campaigns'):
            suggestions.append("Consider improving ad headlines for low CTR campaigns")

        if context.get('high_cpa_campaigns'):
            suggestions.append("Review targeting and bids for high CPA campaigns")

        if context.get('budget_pacing_issues'):
            suggestions.append("Adjust daily budgets to maintain consistent delivery")

        if not suggestions:
            suggestions.append("Campaigns are performing well. Continue current strategy.")

        return "\n".join(f"💡 {suggestion}" for suggestion in suggestions)

    def format_telegram_report(self, date: str, campaigns: List[Dict[str, Any]],
                              keywords: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
        """Format report as Telegram message."""
        report = f"📊 *Google Ads Daily Report - {date}*\n\n"
        report += f"📈 *Account Summary*\n"
        report += f"Campaigns: {summary['active_campaigns']} | "
        report += f"Impressions: {summary['total_impressions']:,} | "
        report += f"Clicks: {summary['total_clicks']:,} | "
        report += f"CTR: {summary['overall_ctr']:.1f}% | "
        report += f"Cost: {fmt_vnd(summary['total_cost'])}"

        if summary['total_conversions'] > 0:
            report += f" | Leads: {summary['total_conversions']}"
            if summary['overall_cpl']:
                report += f" | CPL: {fmt_vnd(summary['overall_cpl'])}"

        report += "\n\n"

        # Per-campaign breakdown
        report += "🔍 *Campaigns*\n"

        low_ctr_campaigns = []
        high_cpa_campaigns = []
        budget_pacing_issues = []

        for campaign in campaigns:
            objective = campaign.get('objective', 'leads')
            campaign_name = campaign['niche'] or campaign['campaign_id']

            if objective == 'leads' and campaign['conversions'] > 0:
                # Lead generation campaign
                report += f"✅ *{campaign_name}* (leads)\n"
                report += f"   Clicks: {campaign['clicks']} | CTR: {campaign['ctr']:.1f}% | "
                report += f"Leads: {campaign['conversions']} | CPL: {fmt_vnd(campaign['cpl'])}\n"
            else:
                # Awareness/traffic campaign
                report += f"📢 *{campaign_name}* (awareness)\n"
                report += f"   Impressions: {campaign['impressions']:,} | Clicks: {campaign['clicks']} | "
                report += f"CTR: {campaign['ctr']:.1f}% | Spend: {fmt_vnd(campaign['cost'])}\n"

            # Add pacing info
            daily_budget = campaign.get('daily_budget', 0)
            pacing_pct = campaign.get('pacing_pct', 0)  # set before the guard:
            # line below uses pacing_pct unconditionally, so it must be defined
            # even when daily_budget==0 (else NameError crashes the daily cron).
            if daily_budget > 0:
                report += f"   Budget: {fmt_vnd(campaign['cost'])}/{fmt_vnd(daily_budget)} daily ({pacing_pct:.0f}%)\n"

            report += "\n"

            # Track issues for suggestions
            if campaign.get('ctr', 0) < 1.0:
                low_ctr_campaigns.append(campaign_name)

            if (campaign.get('cpl') and campaign.get('daily_budget', 0) > 0 and
                campaign['cpl'] > campaign['daily_budget'] * 0.5):
                high_cpa_campaigns.append(campaign_name)

            if pacing_pct > 120 or pacing_pct < 50:
                budget_pacing_issues.append(campaign_name)

        # Top keywords
        if keywords:
            report += "🔑 *Top Keywords*\n"
            for i, keyword in enumerate(keywords, 1):
                report += f"{i}. *{keyword['keyword']}* ({keyword['match_type']})\n"
                report += f"   Clicks: {keyword['clicks']} | Conversions: {keyword['conversions']} | CPC: {fmt_vnd(keyword['avg_cpc'])}\n"
            report += "\n"

        # LLM suggestions
        context = {
            'low_ctr_campaigns': low_ctr_campaigns,
            'high_cpa_campaigns': high_cpa_campaigns,
            'budget_pacing_issues': budget_pacing_issues,
            'summary': summary
        }

        suggestions = self.llm_generate_suggestions(context)
        if suggestions:
            report += "ℹ️ *Ghi chú heuristic (LLM chưa wire)*\n"
            report += suggestions + "\n\n"

        # Footer
        report += f"📅 Report generated at {datetime.now().strftime('%H:%M UTC')}\n"
        report += f"🤖 Powered by Hermes Agent"

        return report

    def send_telegram_message(self, message: str) -> bool:
        """Send message to Telegram."""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("[Telegram] Bot token or chat ID not configured")
            return False

        try:
            import requests

            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }

            response = requests.post(url, json=data, timeout=10)
            if response.status_code == 200:
                print("[Telegram] Message sent successfully")
                return True
            else:
                print(f"[Telegram] Error sending message: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"[Telegram] Error: {e}")
            return False

    def generate_report(self, date: str = None, send_to_telegram: bool = True) -> str:
        """Generate and optionally send daily report."""
        if not date:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"[Report] Generating report for {date}")

        # Get data
        campaigns = self.get_per_campaign_kpis(date)
        keywords = self.get_top_keywords(date)
        summary = self.get_account_summary(date)

        if not campaigns:
            print(f"[Report] No campaign data found for {date}")
            return "No campaign data found for the selected date."

        # Format report
        report = self.format_telegram_report(date, campaigns, keywords, summary)

        # Print to console
        print("\n" + "="*50)
        print(report)
        print("="*50 + "\n")

        # Send to Telegram
        if send_to_telegram:
            success = self.send_telegram_message(report)
            if success:
                print("[Report] Report sent to Telegram")
            else:
                print("[Report] Failed to send report to Telegram")

        return report

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print("[Report] Database connection closed")


def main():
    """Main entry point."""
    load_google_ads_env()  # TELEGRAM_* live in google-ads.env; load so cron works
    parser = argparse.ArgumentParser(description='Generate daily Google Ads report')
    parser.add_argument('--date', type=str, help='Date in YYYY-MM-DD format (default: yesterday)')
    parser.add_argument('--db-path', type=Path,
                       default=Path('data/campaigns-local.db'),
                       help='Database path')
    parser.add_argument('--no-telegram', action='store_true',
                       help='Do not send to Telegram')

    args = parser.parse_args()

    # Initialize report generator
    generator = DailyReportGenerator(args.db_path)

    try:
        report = generator.generate_report(
            date=args.date,
            send_to_telegram=not args.no_telegram
        )

        # Save report to file
        report_path = args.db_path.parent / f"daily-report-{args.date or datetime.now().strftime('%Y-%m-%d')}.md"
        with open(report_path, 'w') as f:
            f.write(report)

        print(f"[Report] Report saved to: {report_path}")

    except Exception as e:
        print(f"[Report] Error: {e}")
        sys.exit(1)
    finally:
        generator.close()


if __name__ == "__main__":
    main()