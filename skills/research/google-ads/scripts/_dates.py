#!/usr/bin/env python3
"""Account-local date helpers (plan wire 6c).

Google Ads `segments.date` is ACCOUNT-LOCAL (the mua-vinfast account is VN =
UTC+7). The monitor's anomaly "today" and the daily report's "yesterday" must
use the SAME account-local day boundary — otherwise a metric row lands on the
wrong day vs the GAQL date and CPA/CTR comparisons drift at the day edge.

GAQL query windows (query_metrics etc.) still use UTC because the API expects
UTC bounds; ONLY the local day-of-comparison uses these helpers.

Timezone comes from env ACCOUNT_TZ (default Asia/Ho_Chi_Minh). zoneinfo is
Python 3.9+ stdlib — no extra deps.
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Ho_Chi_Minh"  # the mua-vinfast VN account


def account_tz() -> ZoneInfo:
    """Account timezone from env ACCOUNT_TZ (default Asia/Ho_Chi_Minh)."""
    name = (os.getenv("ACCOUNT_TZ") or DEFAULT_TZ).strip() or DEFAULT_TZ
    try:
        return ZoneInfo(name)
    except Exception:
        # Unknown tz string → fall back to the VN default rather than crashing cron.
        return ZoneInfo(DEFAULT_TZ)


def account_local_now() -> datetime:
    """Current time in the account timezone (timezone-aware)."""
    return datetime.now(account_tz())


def account_local_today() -> str:
    """Today's date (YYYY-MM-DD) in the account timezone."""
    return account_local_now().strftime("%Y-%m-%d")
