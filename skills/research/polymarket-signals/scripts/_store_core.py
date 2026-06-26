#!/usr/bin/env python3
"""Core DB connection, locking, write operations for polymarket-signals store.

Reads in _store_reads.py. Facade re-exports in store.py.
"""

import contextlib
import fcntl
import json
import sqlite3
import stat
import sys
from pathlib import Path

from _paths import get_db_path, get_db_lock_path
from _schema import SCHEMA_VERSION, DDL_TABLES, DDL_INDEXES, DDL_SEED, MIGRATIONS

_LOCK_FDS: dict[int, object] = {}


def _lock_db() -> None:
    p = get_db_lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = open(p, "w")  # noqa: SIM115
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FDS[id(fd)] = fd
    except (BlockingIOError, OSError):
        fd.close()
        print("DB locked by another process", file=sys.stderr)
        sys.exit(1)


def _unlock_db() -> None:
    for fd in list(_LOCK_FDS.values()):
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        except OSError:
            pass
    _LOCK_FDS.clear()


def _connect() -> sqlite3.Connection:
    db = get_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


@contextlib.contextmanager
def _locked_session(commit: bool):
    """Acquire lock, yield connection. commit=True persists before close."""
    _lock_db()
    try:
        c = _connect()
        try:
            yield c
            if commit:
                c.commit()
        finally:
            c.close()
    finally:
        _unlock_db()


_w = lambda: _locked_session(True)
_r = lambda: _locked_session(False)


# ── Init ──────────────────────────────────────────────────────────────────────


def init_db() -> None:
    """Idempotent DB init: tables + migrations + integrity check."""
    _lock_db()
    try:
        c = _connect()
        ok = c.execute("PRAGMA integrity_check").fetchone()
        if not ok or ok[0] != "ok":
            print(f"DB integrity check failed: {ok[0]}", file=sys.stderr)
            sys.exit(1)
        c.executescript(DDL_TABLES)
        c.executescript(DDL_INDEXES)
        c.execute(DDL_SEED, ("schema_version", str(SCHEMA_VERSION)))
        row = c.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        cur = int(row[0]) if row else SCHEMA_VERSION
        for to_v, sql in MIGRATIONS:
            if cur < to_v:
                c.execute(sql)
                cur = to_v
        c.commit()
        c.close()
        db = get_db_path()
        if db.exists():
            db.chmod(stat.S_IRUSR | stat.S_IWUSR)
    finally:
        _unlock_db()


# ── Write Operations ─────────────────────────────────────────────────────────


def upsert_market(
    condition_id: str, slug: str, question: str, category: str,
    clob_token_ids: str, outcome_prices: str, volume_usd: float,
    end_date: str, source_first_seen: str,
    category_confidence: float = 1.0,
) -> None:
    with _w() as c:
        c.execute(
            """INSERT INTO markets(condition_id, slug, question, category,
               clob_token_ids, outcome_prices, volume_usd, end_date,
               source_first_seen, category_confidence)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(condition_id) DO UPDATE SET
               slug=excluded.slug, question=excluded.question,
               category=excluded.category, volume_usd=excluded.volume_usd,
               end_date=excluded.end_date, clob_token_ids=excluded.clob_token_ids,
               outcome_prices=excluded.outcome_prices,
               source_first_seen=excluded.source_first_seen,
               category_confidence=excluded.category_confidence""",
            (condition_id, slug, question, category, clob_token_ids,
             outcome_prices, volume_usd, end_date, source_first_seen,
             category_confidence))


def create_scan(ts: str, status: str = "running") -> int:
    with _w() as c:
        return c.execute("INSERT INTO scans(ts, status) VALUES(?, ?)", (ts, status)).lastrowid


def insert_prediction(condition_id: str, scan_id: int,
                      status: str = "pending", **kw) -> int:
    with _w() as c:
        return c.execute(
            """INSERT OR IGNORE INTO predictions(
                condition_id, scan_id, status, predicted_p, market_p,
                confidence, sources, rationale, category, scan_ts)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (condition_id, scan_id, status, kw.get("predicted_p"),
             kw.get("market_p"), kw.get("confidence"),
             kw.get("sources", "[]"), kw.get("rationale"),
             kw.get("category"), kw.get("scan_ts"))).lastrowid


def update_prediction(pred_id: int, status: str = "done", **kw) -> None:
    with _w() as c:
        c.execute(
            """UPDATE predictions SET status=?, predicted_p=?, market_p=?,
               confidence=?, sources=?, rationale=?, category=? WHERE id=?""",
            (status, kw.get("predicted_p"), kw.get("market_p"),
             kw.get("confidence"), kw.get("sources"),
             kw.get("rationale"), kw.get("category"), pred_id))


def set_ensemble_breakdown(pred_id: int, breakdown: dict) -> None:
    with _w() as c:
        c.execute("UPDATE predictions SET ensemble_breakdown=? WHERE id=?",
                  (json.dumps(breakdown), pred_id))


def mark_outcome(condition_id: str, outcome_int: int, resolved_ts: str,
                 resolution_source: str, outcome_confidence: float = 1.0,
                 outcome_raw: str = "",
                 resolution_status: str = "resolved") -> None:
    with _w() as c:
        existing = c.execute(
            "SELECT outcome_int FROM outcomes WHERE condition_id=?",
            (condition_id,)).fetchone()
        prev = existing[0] if existing else None
        c.execute(
            """INSERT OR REPLACE INTO outcomes(
                condition_id, outcome_int, resolved_ts, resolution_source,
                outcome_confidence, outcome_raw, resolution_status,
                previous_outcome_int) VALUES(?,?,?,?,?,?,?,?)""",
            (condition_id, outcome_int, resolved_ts, resolution_source,
             outcome_confidence, outcome_raw, resolution_status, prev))


def finish_scan(scan_id: int, n_markets: int, categories: list,
                cost_note: str = "", status: str = "done") -> None:
    with _w() as c:
        c.execute(
            "UPDATE scans SET n_markets=?,categories=?,cost_note=?,status=? WHERE id=?",
            (n_markets, json.dumps(categories), cost_note, status, scan_id))


def recategorize(condition_id: str, category: str) -> None:
    with _w() as c:
        c.execute("UPDATE markets SET category_override=? WHERE condition_id=?",
                  (category, condition_id))
