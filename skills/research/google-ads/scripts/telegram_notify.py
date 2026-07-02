#!/usr/bin/env python3
"""Telegram notifications for the google-ads skill — TWO channels.

Routing (per user spec):
- REPORT/LEAD channel → Rem-chan bot → "Vinfast ADS Notify" group.
  Used by daily_report.py (own sender reading TELEGRAM_BOT_TOKEN/CHAT_ID) and
  send_text() here (future anomaly/lead pings).
- APPROVAL channel    → Violet-chan bot → user DM (interactive: needs a human
  to approve/reject/deploy). Used by send_approval_request, send_deploy_result,
  send_approval_text.

Creds live in google-ads.env:
- Report:   TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID               (Rem-chan + group)
- Approval: TELEGRAM_APPROVAL_TOKEN + TELEGRAM_APPROVAL_CHAT_ID (Violet-chan + user DM)
Approval falls back to report creds if its dedicated vars are unset (so old
configs still notify somewhere instead of silently skipping). Dedicated
approval var names are robust against gateway env injection: the gateway's
Violet-chan token can never clobber the report bot (different var names, no
setdefault collision).
"""
from __future__ import annotations
import os

import requests

TG_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MSG = 4096  # Telegram hard limit per message


def _report_creds() -> tuple[str, str] | None:
    """Report/lead channel (Rem-chan → group). None if unset (best-effort)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id:
        return None
    return token, chat_id


def _approval_creds() -> tuple[str, str] | None:
    """Approval/deploy channel (Violet-chan → user DM).

    Dedicated vars TELEGRAM_APPROVAL_TOKEN/CHAT_ID. Falls back to the report
    channel when unset, so a not-yet-configured approval channel still notifies
    somewhere rather than silently dropping the approval request.
    """
    token = os.getenv("TELEGRAM_APPROVAL_TOKEN")
    chat_id = os.getenv("TELEGRAM_APPROVAL_CHAT_ID")
    if token and chat_id:
        return token, chat_id
    return _report_creds()


_creds = _report_creds  # backward-compat alias for any internal callers


def _post(text: str, creds) -> bool:
    """Send text to explicit (token, chat_id). Chunks >4096 chars. Best-effort:
    never raises — prints a warning + returns False on missing creds or failure."""
    if not creds:
        print("[TELEGRAM] creds unset — skipping notify.")
        return False
    token, chat_id = creds
    ok = True
    for i in range(0, len(text), MAX_MSG):
        chunk = text[i:i + MAX_MSG]
        try:
            resp = requests.post(
                TG_API.format(token=token),
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
                timeout=15,
            )
            if resp.status_code != 200:
                # Retry without Markdown if parse-mode rejected (bad chars).
                if "parse" in resp.text.lower():
                    resp = requests.post(
                        TG_API.format(token=token),
                        json={"chat_id": chat_id, "text": chunk},
                        timeout=15,
                    )
                if resp.status_code != 200:
                    print(f"[TELEGRAM] send failed ({resp.status_code}): "
                          f"{resp.text[:200]}")
                    ok = False
        except requests.RequestException as e:
            print(f"[TELEGRAM] send error: {e}")
            ok = False
    return ok


def send_text(text: str) -> bool:
    """Report/lead channel (Rem-chan → Vinfast ADS Notify group)."""
    return _post(text, _report_creds())


def send_anomaly(anomaly_type: str, entity_name: str, metric_name: str,
                 current: float, baseline: float, change_pct: float) -> bool:
    """Ping the REPORT channel about a detected anomaly (wire 4).

    Best-effort: never raises. Returns False on missing creds or send failure so
    monitor sync is never blocked by a Telegram outage.
    """
    arrow = "▲" if change_pct >= 0 else "▼"
    text = (
        f"⚠️ *ANOMALY: {anomaly_type}*\n"
        f"`{entity_name}` — {metric_name}\n"
        f"{arrow} {current:.2f} vs baseline {baseline:.2f} ({change_pct:+.1f}%)"
    )
    return _post(text, _report_creds())


def send_approval_text(text: str) -> bool:
    """Approval/deploy channel (Violet-chan → user DM)."""
    return _post(text, _approval_creds())


def send_approval_request(uuid_: str, niche: str, variations: list[dict],
                           campaign_id: str) -> bool:
    """Notify (via Violet-chan DM) that ad copy awaits approval + approve cmd."""
    lines = [f"🎯 *Ad copy chờ duyệt — {niche}*",
             f"Campaign: `{campaign_id}`",
             f"📦 `{len(variations)}` variations đã pass policy screening",
             ""]
    for i, v in enumerate(variations, 1):
        h = v.get("headlines", ["?"])[0][:60]
        lines.append(f"{i}. {h}")
    lines += ["",
              f"ID: `{uuid_}`",
              f"✅ Duyệt: `creator.py --approve {uuid_} --indices 1,3`",
              f"❌ Từ chối: `creator.py --reject {uuid_}`",
              f"⏰ Hết hạn sau 24h"]
    return send_approval_text("\n".join(lines))


def send_deploy_result(uuid_: str, success: bool, detail: str = "") -> bool:
    """Notify (via Violet-chan DM) of an approve→deploy outcome."""
    icon = "✅" if success else "❌"
    msg = f"{icon} Deploy {'thành công' if success else 'thất bại'} (ID `{uuid_}`)"
    if detail:
        msg += f"\n{detail}"
    return send_approval_text(msg)
