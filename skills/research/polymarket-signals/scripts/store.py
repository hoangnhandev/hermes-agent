#!/usr/bin/env python3
"""SQLite store for polymarket-signals skill.

Thin facade re-exporting _store_core (writes) + _store_reads (reads).
All CRUD goes through this module — no direct sqlite3 elsewhere.

Usage:
    python3 store.py init | dump-predictions | stats
"""

import argparse
import json

# Re-export all public symbols so `import store` works everywhere
from _store_core import (  # noqa: F401
    init_db, upsert_market, create_scan, insert_prediction,
    update_prediction, set_ensemble_breakdown, mark_outcome,
    finish_scan, recategorize, _connect, _lock_db, _unlock_db, _r,
)
from _store_reads import get_predictions, get_pending_resolution  # noqa: F401
from _paths import get_db_path

# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Polymarket signals store")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("init")
    d = sub.add_parser("dump-predictions")
    d.add_argument("--category")
    d.add_argument("--limit", type=int)
    sub.add_parser("stats")
    args = p.parse_args()
    if args.cmd == "init":
        init_db()
        print(f"DB initialized at {get_db_path()}")
    elif args.cmd == "dump-predictions":
        for r in get_predictions(category=args.category, limit=args.limit):
            print(json.dumps(r, default=str, ensure_ascii=False))
    elif args.cmd == "stats":
        init_db()
        c = _connect()
        np = c.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        nd = c.execute("SELECT COUNT(*) FROM predictions WHERE status='done'").fetchone()[0]
        no = c.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
        nm = c.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
        cats = c.execute(
            "SELECT category,COUNT(*) c FROM predictions GROUP BY category"
        ).fetchall()
        c.close()
        print(f"Markets:{nm}  Predictions:{np} (done:{nd})  Outcomes:{no}")
        for cat, n in cats:
            print(f"  {cat}: {n}")
    else:
        p.print_help()
