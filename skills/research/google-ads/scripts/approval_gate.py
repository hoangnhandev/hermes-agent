#!/usr/bin/env python3
"""Async approval gate for creator.py — pending-file CRUD + expiry.

Headless-safe replacement for blocking input(). creator generates ad copy →
writes a pending record → Telegram notifies (text) → exits. Human resumes via
`creator.py --approve <uuid> --indices 1,3` (CLI-first; Telegram inline-button
flow deferred to a future phase).

Pending records live in data/pending-approvals/<uuid>.json. Atomic writes
(tmp+rename). 24h expiry. UUID via secrets.token_hex (unguessable).
"""
from __future__ import annotations
import json
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

PENDING_DIR = Path(__file__).parent.parent / "data" / "pending-approvals"
EXPIRY_HOURS = 24
STATUSES = ("pending", "approved", "deployed", "rejected", "expired")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def write_pending(plan_path: str, niche: str, variations: list[dict],
                  campaign_id: str) -> str:
    """Persist a pending approval record. Returns the uuid."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    uuid_ = secrets.token_hex(8)
    now = _now()
    record = {
        "uuid": uuid_,
        "plan_path": str(plan_path),
        "niche": niche,
        "campaign_id": campaign_id,
        "variations": variations,
        "selected_indices": [],
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=EXPIRY_HOURS)).isoformat(),
    }
    fp = PENDING_DIR / f"{uuid_}.json"
    tmp = fp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(fp)  # atomic
    return uuid_


def read_pending(uuid_: str) -> dict | None:
    """Read a pending record by uuid (None if missing/expired)."""
    fp = PENDING_DIR / f"{uuid_}.json"
    if not fp.exists():
        return None
    try:
        rec = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    # Auto-expire: if past expires_at and still pending, mark expired.
    if rec.get("status") == "pending":
        try:
            exp = datetime.fromisoformat(rec["expires_at"])
            if _now() > exp:
                rec["status"] = "expired"
                mark_status(uuid_, "expired")
        except (KeyError, ValueError):
            pass
    return rec


def mark_status(uuid_: str, status: str, selected_indices: list[int] | None = None) -> bool:
    """Update a pending record's status (and optionally selected_indices)."""
    if status not in STATUSES:
        raise ValueError(f"invalid status {status!r}; valid: {STATUSES}")
    fp = PENDING_DIR / f"{uuid_}.json"
    if not fp.exists():
        return False
    rec = json.loads(fp.read_text(encoding="utf-8"))
    rec["status"] = status
    rec["updated_at"] = _now().isoformat()
    if selected_indices is not None:
        rec["selected_indices"] = selected_indices
    tmp = fp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(fp)
    return True


def sweep_expired() -> int:
    """Mark all pending records past expiry as expired. Returns count swept."""
    if not PENDING_DIR.exists():
        return 0
    now = _now()
    n = 0
    for fp in PENDING_DIR.glob("*.json"):
        try:
            rec = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if rec.get("status") == "pending":
            try:
                if now > datetime.fromisoformat(rec["expires_at"]):
                    mark_status(rec["uuid"], "expired")
                    n += 1
            except (KeyError, ValueError):
                pass
    return n
