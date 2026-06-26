#!/usr/bin/env python3
"""Resolution client — check resolved markets and record outcomes.

Finds markets with predictions but no outcome, fetches resolution data
from Gamma, and calls store.mark_outcome().

Usage:
    python3 resolution_client.py check [--limit 100]
    python3 resolution_client.py show-pending
"""

import argparse
import json
import sys
from datetime import datetime, timezone

import store as s
from _http import GAMMA, _build_gamma_url, _get_safe, _parse_json_field


def _extract_outcome(market: dict) -> dict | None:
    """Extract outcome from a Gamma market dict.

    Returns {outcome_int, resolution_source, outcome_confidence,
             outcome_raw, resolution_status} or None if not resolvable.

    Quarantines void/disputed/ambiguous/non-binary outcomes (F-06).
    """
    closed = market.get("closed", False)
    if not closed:
        return None

    # Parse outcome prices to determine resolution
    prices_raw = market.get("outcomePrices", "[]")
    prices = _parse_json_field(prices_raw)
    if not isinstance(prices, list) or len(prices) < 2:
        return None

    try:
        yes_p = float(prices[0])
        no_p = float(prices[1])
    except (ValueError, TypeError):
        return None

    # Binary resolution: yes wins if yes_price == 1.0, no wins if no_price == 1.0
    if yes_p >= 0.999:
        outcome_int = 1
    elif no_p >= 0.999:
        outcome_int = 0
    else:
        # Non-binary / void / disputed — quarantine
        return {
            "outcome_int": None,
            "resolution_source": "gamma",
            "outcome_confidence": 0.0,
            "outcome_raw": json.dumps(market, default=str)[:1000],
            "resolution_status": "ambiguous",
        }

    # UMA finalized or standard Gamma resolution
    return {
        "outcome_int": outcome_int,
        "resolution_source": "gamma",
        "outcome_confidence": 1.0,
        "outcome_raw": json.dumps(market, default=str)[:1000],
        "resolution_status": "resolved",
    }


def fetch_resolved(since_ts: str = None, limit: int = 100) -> list[dict]:
    """Fetch recently closed markets from Gamma. Returns normalized outcome dicts."""
    params = {
        "closed": "true",
        "order": "endDate",
        "ascending": "false",
        "limit": limit,
    }
    if since_ts:
        params["end_date_min"] = since_ts

    url = _build_gamma_url("/markets", params)
    markets = _get_safe(url, timeout=15)
    if not isinstance(markets, list):
        return []

    results = []
    for m in markets:
        cid = m.get("conditionId") or m.get("condition_id")
        if not cid:
            continue
        outcome = _extract_outcome(m)
        if outcome is None:
            continue
        outcome["condition_id"] = cid
        results.append(outcome)

    return results


def run_resolution_check(limit: int = 100) -> dict:
    """Check pending resolutions and record outcomes. Returns summary."""
    s.init_db()
    pending = s.get_pending_resolution(limit=limit)
    if not pending:
        return {"n_resolved": 0, "n_quarantined": 0, "errors": 0}

    ts = datetime.now(timezone.utc).isoformat()

    # Build a set of condition_ids to look up
    cids = {p["condition_id"] for p in pending}

    # Fetch closed markets from Gamma
    resolved = fetch_resolved(limit=limit * 2)  # over-fetch to improve match rate
    # Partition resolved vs quarantined by whether outcome_int is set
    resolved_map = {r["condition_id"]: r for r in resolved if r.get("outcome_int") is not None}
    quarantined_map = {r["condition_id"]: r for r in resolved if r.get("outcome_int") is None}

    n_resolved = 0
    n_quarantined = 0
    errors = 0

    # Both branches call mark_outcome identically; only the counter differs
    for cid in cids:
        outcome = resolved_map.get(cid) or quarantined_map.get(cid)
        if outcome is None:
            continue
        try:
            s.mark_outcome(
                cid, outcome["outcome_int"], ts, outcome["resolution_source"],
                outcome["outcome_confidence"], outcome["outcome_raw"],
                outcome["resolution_status"],
            )
            if cid in resolved_map:
                n_resolved += 1
            else:
                n_quarantined += 1
        except Exception as e:
            print(f"Error recording outcome for {cid[:20]}: {e}", file=sys.stderr)
            errors += 1

    return {
        "n_resolved": n_resolved,
        "n_quarantined": n_quarantined,
        "errors": errors,
    }


def main():
    p = argparse.ArgumentParser(description="Check market resolutions")
    sub = p.add_subparsers(dest="cmd")
    ck = sub.add_parser("check")
    ck.add_argument("--limit", type=int, default=100)
    sp = sub.add_parser("show-pending")
    sp.add_argument("--limit", type=int, default=20)
    args = p.parse_args()

    if args.cmd == "check":
        result = run_resolution_check(args.limit)
        print(f"Resolution check: {result['n_resolved']} resolved, "
              f"{result['n_quarantined']} quarantined, {result['errors']} errors")

    elif args.cmd == "show-pending":
        s.init_db()
        pending = s.get_pending_resolution(limit=args.limit)
        if not pending:
            print("No markets pending resolution.")
        else:
            print(f"{len(pending)} markets pending resolution:")
            for p_entry in pending:
                print(f"  {p_entry['condition_id'][:30]}...  [{p_entry['category']}]  "
                      f"last_scan: {p_entry.get('scan_ts', '?')}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
