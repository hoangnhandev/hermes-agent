#!/usr/bin/env python3
"""Read operations for polymarket-signals store.

Uses _r() read-only context from _store_core for safe concurrent reads.
"""

from _store_core import _r


def get_predictions(category: str = None, resolved_only: bool = False,
                    limit: int = None) -> list[dict]:
    with _r() as c:
        q = """SELECT p.*, o.outcome_int, o.resolution_status
              FROM predictions p
              LEFT JOIN outcomes o ON p.condition_id = o.condition_id"""
        conds, params = [], []
        if category:
            conds.append("p.category = ?")
            params.append(category)
        if resolved_only:
            conds.append("o.outcome_int IS NOT NULL")
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY p.scan_ts DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        rows = c.execute(q, params).fetchall()
        return [dict(r) for r in rows]


def get_pending_resolution(limit: int = None) -> list[dict]:
    with _r() as c:
        q = """SELECT DISTINCT p.condition_id, p.category, p.scan_ts
              FROM predictions p
              LEFT JOIN outcomes o ON p.condition_id = o.condition_id
              WHERE o.condition_id IS NULL"""
        if limit:
            q += f" LIMIT {int(limit)}"
        rows = c.execute(q).fetchall()
        return [dict(r) for r in rows]
