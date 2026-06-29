#!/usr/bin/env python3
"""Dashboard data layer — read-only metrics from polymarket-signals SQLite.

Opens a mode=ro WAL connection (never blocks the scan writer).
Computes calibration bins, Brier scores, edge distribution, active signals,
resolution health, and header stats into a single plain dict for the renderer.

CRITICAL: Do NOT import _store_core — its _r() takes flock and sys.exit(1)
on contention, which would kill the dashboard when a scan is mid-write.
"""

import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

from _paths import get_db_path

# Calibration bin edges (0.0 to 1.0 in 0.1 steps)
CALIBRATION_BINS = [i / 10 for i in range(11)]  # [0.0, 0.1, ..., 1.0]
MIN_RESOLVED_FOR_CALIBRATION = 30
EDGE_THRESHOLD = 0.10
MAX_RECENT_PREDICTIONS = 50
MAX_ACTIVE_SIGNALS = 20


def open_ro(db_path: Path | str | None = None) -> sqlite3.Connection | None:
    """Open a read-only WAL connection. Returns None on failure (never exits)."""
    if db_path is None:
        db_path = get_db_path()
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro", uri=True, timeout=10
        )
        conn.execute("PRAGMA query_only=1")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError:
        return None


def _query_done_predictions(conn: sqlite3.Connection) -> list[dict]:
    """Fetch predictions from completed scans only, deduped by condition_id."""
    rows = conn.execute("""
        SELECT p.*, m.question, m.slug,
               o.outcome_int, o.resolution_status, o.resolved_ts
        FROM predictions p
        JOIN markets m ON p.condition_id = m.condition_id
        LEFT JOIN outcomes o ON p.condition_id = o.condition_id
        JOIN scans s ON p.scan_id = s.id
        WHERE s.status = 'done'
        ORDER BY p.scan_id DESC
    """).fetchall()
    # De-dup: keep latest scan_id per condition_id
    seen: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        cid = d["condition_id"]
        if cid not in seen:
            seen[cid] = d
    return list(seen.values())


def _query_resolved(predictions: list[dict]) -> list[dict]:
    """Filter to resolved predictions with valid outcome_int (0 or 1)."""
    return [
        p for p in predictions
        if p.get("outcome_int") is not None and p["outcome_int"] in (0, 1)
    ]


def _compute_brier(resolved: list[dict]) -> dict:
    """Mean Brier score: (predicted_p - outcome_int)^2. Per-category + overall."""
    if not resolved:
        return {"overall": None, "per_category": {}}
    errors = [(r["predicted_p"] - r["outcome_int"]) ** 2 for r in resolved]
    overall = statistics.mean(errors)
    by_cat: dict[str, list[float]] = defaultdict(list)
    for r, e in zip(resolved, errors):
        cat = r.get("category") or "unknown"
        by_cat[cat].append(e)
    per_category = {cat: statistics.mean(errs) for cat, errs in by_cat.items()}
    return {"overall": overall, "per_category": per_category}


def _compute_calibration(resolved: list[dict]) -> list[dict]:
    """Bin predicted_p into fixed bins; return bin stats with n and freq."""
    bins = []
    for i in range(len(CALIBRATION_BINS) - 1):
        lo = CALIBRATION_BINS[i]
        hi = CALIBRATION_BINS[i + 1]
        members = [
            r for r in resolved
            if lo <= r["predicted_p"] < hi
            or (i == len(CALIBRATION_BINS) - 2 and r["predicted_p"] == hi)
        ]
        n = len(members)
        freq = statistics.mean([r["outcome_int"] for r in members]) if n else None
        bins.append({"bin_lo": lo, "bin_hi": hi, "n": n, "freq": freq})
    return bins


def _compute_edge_distribution(predictions: list[dict]) -> dict:
    """Edge = predicted_p - market_p. Histogram counts + per-category."""
    edges = []
    by_cat: dict[str, list[float]] = defaultdict(list)
    for p in predictions:
        if p.get("market_p") is None or p.get("predicted_p") is None:
            continue
        edge = p["predicted_p"] - p["market_p"]
        edges.append(edge)
        cat = p.get("category") or "unknown"
        by_cat[cat].append(edge)
    if not edges:
        return {"edges": [], "histogram": [], "per_category": {}}
    # Build histogram with 20 bins from -1 to 1
    n_bins = 20
    bin_width = 2.0 / n_bins
    hist_counts = [0] * n_bins
    for e in edges:
        idx = int((e + 1.0) / bin_width)
        idx = max(0, min(n_bins - 1, idx))
        hist_counts[idx] += 1
    histogram = [
        {"bin_lo": -1.0 + i * bin_width, "bin_hi": -1.0 + (i + 1) * bin_width, "count": c}
        for i, c in enumerate(hist_counts)
    ]
    per_cat = {}
    for cat, cat_edges in by_cat.items():
        per_cat[cat] = {
            "mean": statistics.mean(cat_edges),
            "count": len(cat_edges),
        }
    return {"edges": edges, "histogram": histogram, "per_category": per_cat}


def _compute_active_signals(predictions: list[dict]) -> list[dict]:
    """Pending predictions with |edge| > threshold, sorted by |edge| desc."""
    pending = [p for p in predictions if p.get("outcome_int") is None]
    signals = []
    for p in pending:
        pred_p = p.get("predicted_p")
        mkt_p = p.get("market_p")
        if pred_p is None or mkt_p is None:
            continue
        edge = pred_p - mkt_p
        if abs(edge) >= EDGE_THRESHOLD:
            signals.append({
                "condition_id": p["condition_id"],
                "question": p.get("question", ""),
                "category": p.get("category", ""),
                "predicted_p": pred_p,
                "market_p": mkt_p,
                "edge": edge,
                "scan_ts": p.get("scan_ts", ""),
            })
    signals.sort(key=lambda x: abs(x["edge"]), reverse=True)
    return signals[:MAX_ACTIVE_SIGNALS]


def _compute_resolution_health(predictions: list[dict]) -> dict:
    """Count resolved / pending / disputed. Return disputed list."""
    resolved = 0
    pending = 0
    disputed = []
    for p in predictions:
        status = p.get("resolution_status", "")
        if status == "resolved" and p.get("outcome_int") is not None:
            resolved += 1
        elif status == "disputed":
            disputed.append(p)
            resolved += 1
        else:
            pending += 1
    return {
        "resolved": resolved,
        "pending": pending,
        "disputed_count": len(disputed),
        "disputed": [
            {
                "condition_id": d["condition_id"],
                "question": d.get("question", ""),
                "resolution_status": d.get("resolution_status", ""),
                "outcome_raw": (d.get("outcome_raw", "") or "")[:200],
            }
            for d in disputed[:10]
        ],
    }


def build_metrics(db_path: Path | str | None = None) -> dict:
    """Build all dashboard metrics from the SQLite store.

    Returns a plain dict ready for the HTML renderer.
    Empty DB → all zeros/None, no exception.
    """
    empty = {
        "total_predictions": 0,
        "resolved_count": 0,
        "pending_count": 0,
        "last_scan_ts": None,
        "mean_brier": None,
        "brier": {"overall": None, "per_category": {}},
        "calibration": [],
        "resolved_predictions": [],
        "edge_distribution": {"edges": [], "histogram": [], "per_category": {}},
        "active_signals": [],
        "recent_predictions": [],
        "resolution_health": {
            "resolved": 0, "pending": 0,
            "disputed_count": 0, "disputed": [],
        },
        "categories": [],
    }

    conn = open_ro(db_path)
    if conn is None:
        return empty

    try:
        predictions = _query_done_predictions(conn)
        if not predictions:
            return empty

        resolved = _query_resolved(predictions)
        brier = _compute_brier(resolved)
        calibration = _compute_calibration(resolved)
        edge_dist = _compute_edge_distribution(predictions)
        active = _compute_active_signals(predictions)
        health = _compute_resolution_health(predictions)

        # Last scan timestamp
        last_scan = conn.execute(
            "SELECT ts FROM scans WHERE status='done' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_scan_ts = last_scan[0] if last_scan else None

        # Categories list
        cats = conn.execute(
            "SELECT DISTINCT category FROM predictions WHERE category IS NOT NULL ORDER BY category"
        ).fetchall()
        categories = [r[0] for r in cats]

        # Recent predictions (cap for scale)
        recent = sorted(predictions, key=lambda x: x.get("scan_ts", ""), reverse=True)
        recent = recent[:MAX_RECENT_PREDICTIONS]
        recent_formatted = [
            {
                "question": r.get("question", ""),
                "category": r.get("category", ""),
                "predicted_p": r.get("predicted_p"),
                "market_p": r.get("market_p"),
                "outcome_int": r.get("outcome_int"),
                "resolution_status": r.get("resolution_status"),
                "scan_ts": r.get("scan_ts", ""),
            }
            for r in recent
        ]

        return {
            "total_predictions": len(predictions),
            "resolved_count": len(resolved),
            "pending_count": health["pending"],
            "last_scan_ts": last_scan_ts,
            "mean_brier": brier["overall"],
            "brier": brier,
            "calibration": calibration,
            "resolved_predictions": resolved,
            "edge_distribution": edge_dist,
            "active_signals": active,
            "recent_predictions": recent_formatted,
            "resolution_health": health,
            "categories": categories,
        }
    except sqlite3.OperationalError:
        return empty
    finally:
        conn.close()


# ── CLI smoke test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    m = build_metrics()
    print(json.dumps(m, indent=2, default=str, ensure_ascii=False))
