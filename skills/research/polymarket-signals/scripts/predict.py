#!/usr/bin/env python3
"""LLM predictor — parse predictions, manage scan lifecycle (agent-driven mode B)."""

import argparse
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone

import store as s
from _alert import (
    format_alert, format_scan_summary, compute_alerts, MAX_RATIONALE_LEN,
)
from markets_client import discover, select_universe

DEFAULT_EDGE_THRESHOLD = 0.10
DEFAULT_MAX_MARKETS = 20
DEFAULT_SHORT_TERM_DAYS = 30
DEFAULT_SHORT_TERM_QUOTA = 10
MAX_ALERTS_PER_SCAN = 5

# Prompt injection defense (F-07)
_BLOCKED = re.compile(
    r"(ignore|instead|you must|system:|new instructions|"
    r"UNTRUSTED_\w+| forget previous|override|"
    r"execute|run command|disregard|reveal|secret)", re.IGNORECASE)


def load_prompt() -> str:
    """Load byte-stable system prompt template."""
    with open(os.path.join(os.path.dirname(__file__), "prompt_template.txt")) as f:
        return f.read()


def wrap_untrusted(text: str) -> tuple[str, str]:
    """Wrap untrusted text in randomized delimiters. Returns (wrapped, nonce)."""
    nonce = secrets.token_hex(8)
    return f"<UNTRUSTED_{nonce}>{text}</UNTRUSTED_{nonce}>", nonce


def predict_one(
    condition_id: str, scan_id: int, market_p: float,
    category: str = "", llm_json: str = None,
) -> dict:
    """Validate LLM JSON and update prediction. Returns prediction dict."""
    ts = datetime.now(timezone.utc).isoformat()

    # Ensure pending row exists (INSERT OR IGNORE if agent skipped it)
    pid = s.insert_prediction(
        condition_id, scan_id, market_p=market_p,
        category=category, scan_ts=ts)
    if not pid:
        # Already exists — find pending row
        preds = s.get_predictions(category=category)
        for p in preds:
            if (p["condition_id"] == condition_id
                    and p["scan_id"] == scan_id
                    and p["status"] == "pending"):
                pid = p["id"]; break

    if not llm_json:
        return {"condition_id": condition_id, "predicted_p": None,
                "market_p": market_p, "category": category, "pred_id": pid}

    try:
        data = json.loads(llm_json)
        predicted_p = float(data.get("predicted_p", 0.5))
        confidence = float(data.get("confidence", 0.5))
        if not (0.0 <= predicted_p <= 1.0) or not (0.0 <= confidence <= 1.0):
            raise ValueError("out of range")
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        err = "out_of_range" if isinstance(e, ValueError) else "invalid_json"
        print(f"Prediction error: {e}", file=sys.stderr)
        s.update_prediction(pid, status="error")
        return {"condition_id": condition_id, "error": err, "pred_id": pid}

    rationale = str(data.get("rationale", ""))[:MAX_RATIONALE_LEN]

    # Prompt injection check (F-07)
    if _BLOCKED.search(rationale):
        rationale = "[rationale sanitized]"

    s.update_prediction(pid, status="done", predicted_p=predicted_p,
                        market_p=market_p, confidence=confidence,
                        sources='["llm","web"]', rationale=rationale,
                        category=category)
    return {
        "condition_id": condition_id, "predicted_p": predicted_p,
        "market_p": market_p, "confidence": confidence,
        "sources": ["llm", "web"], "rationale": rationale,
        "category": category, "pred_id": pid,
    }

def run_scan(
    categories: list[str] = None,
    min_liquidity: float = 5000.0,
    min_volume: float = 10000.0,
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
    limit: int = 100,
    max_markets: int = DEFAULT_MAX_MARKETS,
    short_term_days: int = DEFAULT_SHORT_TERM_DAYS,
    short_term_quota: int = DEFAULT_SHORT_TERM_QUOTA,
    dry_run: bool = False,
) -> dict:
    """Discover markets, create scan, insert pending rows. Cap by max_markets.

    Reserves ``short_term_quota`` slots for markets resolving within
    ``short_term_days`` so outcomes (and calibration data) accumulate quickly.
    """
    s.init_db()
    ts = datetime.now(timezone.utc).isoformat()
    scan_id = s.create_scan(ts, status="running")

    markets = select_universe(
        categories, min_liquidity, min_volume, limit,
        max_markets, short_term_days, short_term_quota,
    )
    by_cat = {}
    n_predicted = 0

    for m in markets:
        cat = m["category"]
        by_cat[cat] = by_cat.get(cat, 0) + 1

        try:
            prices = json.loads(m["outcome_prices"]) if isinstance(m["outcome_prices"], str) else m["outcome_prices"]
            market_p = float(prices[0]) if prices else 0.5
        except (json.JSONDecodeError, ValueError, TypeError):
            market_p = 0.5

        pid = s.insert_prediction(
            m["condition_id"], scan_id, status="pending",
            market_p=market_p, category=cat, scan_ts=ts,
        )
        if pid:
            n_predicted += 1
            if dry_run:
                s.update_prediction(pid, status="done", predicted_p=None,
                                    market_p=market_p, category=cat,
                                    sources='[]', rationale="dry-run")

    s.finish_scan(scan_id, n_predicted, list(by_cat.keys()),
                  f"dry_run={dry_run}")
    return {
        "n_scanned": len(markets), "n_predicted": n_predicted,
        "n_alerted": 0, "ts": ts, "scan_id": scan_id,
        "cost_note": f"dry_run={dry_run}, max_markets={max_markets}",
        "markets": markets[:MAX_ALERTS_PER_SCAN],
    }
def complete_scan(scan_id: int) -> dict:
    """Update a running scan to done with final counts."""
    s.init_db()
    conn = s._connect()
    row = conn.execute("SELECT n_markets FROM scans WHERE id=?", (scan_id,)).fetchone()
    conn.close()
    return {"scan_id": scan_id, "status": "done",
            "n_markets": row[0] if row else 0}

def _add_scan_args(p):
    p.add_argument("--categories", default="crypto,politics")
    p.add_argument("--min-liquidity", type=float, default=5000)
    p.add_argument("--min-volume", type=float, default=10000)
    p.add_argument("--edge-threshold", type=float, default=DEFAULT_EDGE_THRESHOLD)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--max-markets", type=int, default=DEFAULT_MAX_MARKETS)
    p.add_argument("--short-term-days", type=int, default=DEFAULT_SHORT_TERM_DAYS)
    p.add_argument("--short-term-quota", type=int, default=DEFAULT_SHORT_TERM_QUOTA)
    p.add_argument("--dry-run", action="store_true")
def main():
    p = argparse.ArgumentParser(description="Polymarket signal predictor")
    sub = p.add_subparsers(dest="cmd")
    rs = sub.add_parser("run-scan"); _add_scan_args(rs)
    po = sub.add_parser("predict-one")
    po.add_argument("--condition-id", required=True)
    po.add_argument("--scan-id", type=int, required=True)
    po.add_argument("--market-p", type=float, default=0.5)
    po.add_argument("--category", default="")
    po.add_argument("--llm-json", default=None)
    fs = sub.add_parser("finish-scan")
    fs.add_argument("--scan-id", type=int, required=True)
    al = sub.add_parser("alerts")
    al.add_argument("--scan-id", type=int, required=True)
    al.add_argument("--edge-threshold", type=float, default=DEFAULT_EDGE_THRESHOLD)
    args = p.parse_args()

    if args.cmd == "run-scan":
        cats = [c.strip() for c in args.categories.split(",")]
        result = run_scan(categories=cats, min_liquidity=args.min_liquidity,
            min_volume=args.min_volume, edge_threshold=args.edge_threshold,
            limit=args.limit, max_markets=args.max_markets,
            short_term_days=args.short_term_days,
            short_term_quota=args.short_term_quota, dry_run=args.dry_run)
        print(f"Scan #{result['scan_id']}: {result['n_predicted']} markets")
        if not args.dry_run and result.get("markets"):
            print(f"MARKETS_JSON_START\n{json.dumps(result['markets'], default=str)}\nMARKETS_JSON_END")
    elif args.cmd == "predict-one":
        print(json.dumps(predict_one(condition_id=args.condition_id,
            scan_id=args.scan_id, market_p=args.market_p,
            category=args.category, llm_json=args.llm_json), default=str))
    elif args.cmd == "finish-scan":
        print(json.dumps(complete_scan(args.scan_id)))
    elif args.cmd == "alerts":
        preds = s.get_predictions()
        scan_preds = [p for p in preds if p.get("scan_id") == args.scan_id]
        alerts = compute_alerts(scan_preds, args.edge_threshold)
        for a in alerts: print(a)
        if not alerts: print("No alerts for this scan.")
        print("\n📊 Xem chi tiết: https://polymarket.withly.org/")
    else:
        p.print_help()
if __name__ == "__main__":
    main()
