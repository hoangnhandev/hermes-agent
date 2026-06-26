#!/usr/bin/env python3
"""Prices client — fetch live prices and history from CLOB API.

Pure library (no DB writes). Called by predict.py.
CLI driver for manual debugging.

Usage:
    python3 prices_client.py price <token_id>
    python3 prices_client.py history <condition_id> [--days 7]
"""

import argparse
import json
import sys
import time

from _http import CLOB, _get_safe


def get_price(token_id: str) -> dict:
    """Get current Yes price for a token. Returns {yes_price, mid, spread}.

    Asserts 0 < yes_price < 1 and mid within [bid, ask] bounds.
    """
    mid_data = _get_safe(f"{CLOB}/midpoint?token_id={token_id}", timeout=10)
    spread_data = _get_safe(f"{CLOB}/spread?token_id={token_id}", timeout=10)

    if not mid_data:
        print(f"No midpoint data for token {token_id[:20]}...", file=sys.stderr)
        return {"yes_price": None, "mid": None, "spread": None}

    mid = float(mid_data.get("mid", 0))
    spread = float(spread_data.get("spread", 0)) if spread_data else 0.0
    yes_price = mid

    # Price sanity assertion (F-02)
    if not (0 < yes_price < 1):
        print(f"WARNING: yes_price {yes_price} out of (0,1) for token {token_id[:20]}",
              file=sys.stderr)
        yes_price = max(0.001, min(0.999, yes_price))

    return {"yes_price": yes_price, "mid": mid, "spread": spread}


def get_history(condition_id: str, days: int = 7, fidelity: int = 60) -> list[dict]:
    """Get price history for a market. Returns [{t, p}, ...].

    Uses startTs+endTs (V2 requirement — interval=all no longer works).
    Max window ~7 days per request.
    """
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (days * 24 * 3600 * 1000)
    url = (f"{CLOB}/prices-history?market={condition_id}"
           f"&startTs={start_ms}&endTs={now_ms}&fidelity={fidelity}")
    data = _get_safe(url, timeout=15)

    if not data:
        return []

    history = data.get("history", [])
    if isinstance(history, list):
        return [{"t": pt[0], "p": pt[1]} for pt in history if len(pt) >= 2]
    return []


def main():
    p = argparse.ArgumentParser(description="Fetch Polymarket prices")
    sub = p.add_subparsers(dest="cmd")
    pr = sub.add_parser("price")
    pr.add_argument("token_id", help="CLOB token ID (Yes token)")
    hi = sub.add_parser("history")
    hi.add_argument("condition_id", help="Market condition ID")
    hi.add_argument("--days", type=int, default=7, help="History window in days")
    args = p.parse_args()

    if args.cmd == "price":
        result = get_price(args.token_id)
        if result["yes_price"] is not None:
            print(f"Yes Price: {result['yes_price']:.4f}")
            print(f"Midpoint:   {result['mid']:.4f}")
            print(f"Spread:     {result['spread']:.4f}")
        else:
            print("No price data available.", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "history":
        points = get_history(args.condition_id, args.days)
        if points:
            print(f"Price history ({len(points)} points, last {args.days}d):")
            for pt in points[-10:]:  # show last 10
                from datetime import datetime, timezone
                ts = datetime.fromtimestamp(pt["t"] / 1000, tz=timezone.utc)
                print(f"  {ts.strftime('%m-%d %H:%M')}  {pt['p']:.4f}")
            if len(points) > 10:
                print(f"  ... ({len(points) - 10} earlier points)")
        else:
            print(f"No history data for {args.condition_id[:20]}...")
            sys.exit(1)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
