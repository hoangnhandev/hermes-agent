#!/usr/bin/env python3
"""Telegram text notifications for the google-ads approval flow.

CLI-first design: this phase sends PLAIN-TEXT messages only (no inline
keyboard / callback handler — that polish is deferred). The notify message
contains the exact approve/reject command for the human to run.
"""
from __future__ import annotations
import os
from typing import Any

import requests

TG_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MSG = 4096  # Telegram hard limit per message


def _creds() -> tuple[str, str] | None:
    """Return (token, chat_id) from env, or None if unset (notify is best-effort)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id:
        return None
    return token, chat_id


def send_text(text: str) -> bool:
    """Send a plain-text Telegram message (chunks if > 4096 chars).

    Returns True if all chunks sent. Best-effort: if creds unset or send fails,
    prints a warning and returns False (never raises — notify is non-critical).
    """
    creds = _creds()
    if not creds:
        print("[TELEGRAM] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set — "
              "skipping notify (set them to receive approval requests).")
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


def send_approval_request(uuid_: str, niche: str, variations: list[dict],
                           campaign_id: str) -> bool:
    """Notify Telegram that ad copy awaits approval (with the approve command)."""
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
    return send_text("\n".join(lines))


def send_deploy_result(uuid_: str, success: bool, detail: str = "") -> bool:
    """Notify Telegram of an approve→deploy outcome."""
    icon = "✅" if success else "❌"
    msg = f"{icon} Deploy {'thành công' if success else 'thất bại'} (ID `{uuid_}`)"
    if detail:
        msg += f"\n{detail}"
    return send_text(msg)
