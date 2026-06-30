#!/usr/bin/env python3
"""Markets client — discover + filter Crypto/Politics markets from Gamma API.

Usage:
    python3 markets_client.py discover --categories crypto,politics [--limit 100]
    python3 markets_client.py scan --categories crypto,politics
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta

import store as s
from _http import (
    GAMMA, _build_gamma_url, _get, _parse_json_field,
    _fmt_pct, _fmt_volume,
)

# Default filter thresholds (behavioral, overridable via CLI flags)
DEFAULT_MIN_LIQUIDITY = 5000.0   # USDC
DEFAULT_MIN_VOLUME = 10000.0     # USDC
DEFAULT_LIMIT = 100              # candidate universe bound

# tag_slug -> our internal category name
TAG_SLUG_MAP = {
    "crypto": "crypto",
    "bitcoin": "crypto",
    "politics": "politics",
    "elections": "politics",
    "us-presidential-election": "politics",
}


def _derive_category(event: dict) -> tuple[str, float]:
    """Derive category from event tags. Returns (category, confidence).

    confidence=1.0 for single canonical tag match; <1.0 for ambiguous/fallback.
    """
    tags = event.get("tags", [])
    slugs = {t.get("slug", "").lower() for t in tags if isinstance(t, dict)}
    matched = set()
    for slug, cat in TAG_SLUG_MAP.items():
        if slug in slugs:
            matched.add(cat)

    if len(matched) == 1:
        return matched.pop(), 1.0
    if len(matched) > 1:
        # Ambiguous — pick first, low confidence
        return sorted(matched)[0], 0.5

    # Fallback: keyword derivation from event slug/title
    slug = event.get("slug", "").lower()
    title = event.get("title", "").lower()
    if any(kw in slug or kw in title for kw in ("bitcoin", "crypto", "eth", "btc")):
        return "crypto", 0.3
    if any(kw in slug or kw in title for kw in ("politic", "election", "vote", "congress")):
        return "politics", 0.3

    return "other", 0.0


def discover(
    categories: list[str] = None,
    min_liquidity: float = DEFAULT_MIN_LIQUIDITY,
    min_volume: float = DEFAULT_MIN_VOLUME,
    limit: int = DEFAULT_LIMIT,
    end_date_max: str = None,
) -> list[dict]:
    """Discover active markets matching category filters.

    Returns list of normalized market dicts with category + confidence.
    """
    categories = categories or ["crypto", "politics"]
    # Map requested categories to tag_slugs
    tag_slugs = set()
    for cat in categories:
        for slug, mapped in TAG_SLUG_MAP.items():
            if mapped == cat:
                tag_slugs.add(slug)

    all_markets = []
    seen = set()
    for slug in tag_slugs:
        params = {
            "tag_slug": slug,
            "active": "true",
            "closed": "false",
            "order": "volume",
            "ascending": "false",
            "limit": limit,
        }
        if end_date_max:
            params["end_date_max"] = end_date_max
        url = _build_gamma_url("/events", params)
        events = _get(url)
        if not isinstance(events, list):
            continue
        for event in events:
            for m in event.get("markets", []):
                cid = m.get("conditionId") or m.get("condition_id")
                if not cid or cid in seen:
                    continue
                seen.add(cid)

                cat, conf = _derive_category(event)
                if cat == "other":
                    continue

                tokens = _parse_json_field(m.get("clobTokenIds", "[]"))
                prices = _parse_json_field(m.get("outcomePrices", "[]"))
                vol = float(m.get("volume", 0) or 0)
                if vol < min_volume:
                    continue

                all_markets.append({
                    "condition_id": cid,
                    "slug": m.get("slug", ""),
                    "question": m.get("question", ""),
                    "category": cat,
                    "category_confidence": conf,
                    "clob_token_ids": json.dumps(tokens) if isinstance(tokens, list) else str(tokens),
                    "outcome_prices": json.dumps(prices) if isinstance(prices, list) else str(prices),
                    "volume_usd": vol,
                    "end_date": m.get("endDate", ""),
                })

    return all_markets


def select_universe(
    categories: list[str] = None,
    min_liquidity: float = DEFAULT_MIN_LIQUIDITY,
    min_volume: float = DEFAULT_MIN_VOLUME,
    limit: int = DEFAULT_LIMIT,
    max_markets: int = 20,
    short_term_days: int = 30,
    short_term_quota: int = 10,
) -> list[dict]:
    """Pick the scan universe with a near-term quota.

    Reserves ``short_term_quota`` slots for markets resolving within
    ``short_term_days`` (so outcomes — and calibration data — accumulate
    quickly instead of waiting on evergreen year-end markets), then fills the
    remaining slots with the top-volume general markets. De-duped by
    condition_id. Pass ``short_term_quota=0`` for the old behaviour.
    """
    quota = max(0, min(short_term_quota, max_markets))
    chosen: list[dict] = []
    seen: set = set()

    # 1) Near-term markets — highest volume among those ending within the window
    if quota > 0 and short_term_days > 0:
        end_max = (datetime.now(timezone.utc) + timedelta(days=short_term_days)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")
        for m in discover(categories, min_liquidity, min_volume, limit,
                          end_date_max=end_max):
            cid = m["condition_id"]
            if cid in seen:
                continue
            seen.add(cid)
            chosen.append(m)
            if len(chosen) >= quota:
                break

    # 2) Fill remaining slots with general top-volume markets
    for m in discover(categories, min_liquidity, min_volume, limit):
        if len(chosen) >= max_markets:
            break
        cid = m["condition_id"]
        if cid in seen:
            continue
        seen.add(cid)
        chosen.append(m)

    return chosen


def run_scan(
    categories: list[str] = None,
    min_liquidity: float = DEFAULT_MIN_LIQUIDITY,
    min_volume: float = DEFAULT_MIN_VOLUME,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Discover markets, persist to store, log scan. Returns summary."""
    s.init_db()
    ts = datetime.now(timezone.utc).isoformat()
    scan_id = s.create_scan(ts, status="running")

    markets = discover(categories, min_liquidity, min_volume, limit)
    by_cat = {}
    for m in markets:
        s.upsert_market(
            m["condition_id"], m["slug"], m["question"], m["category"],
            m["clob_token_ids"], m["outcome_prices"], m["volume_usd"],
            m["end_date"], ts, m["category_confidence"],
        )
        by_cat[m["category"]] = by_cat.get(m["category"], 0) + 1

    s.finish_scan(scan_id, len(markets), list(by_cat.keys()), status="done")
    return {
        "n_markets": len(markets),
        "by_category": by_cat,
        "ts": ts,
        "scan_id": scan_id,
    }


def _add_filter_args(parser):
    """Add shared category filter arguments to a subparser."""
    parser.add_argument("--categories", default="crypto,politics",
                       help="Comma-separated category slugs")
    parser.add_argument("--min-liquidity", type=float, default=DEFAULT_MIN_LIQUIDITY)
    parser.add_argument("--min-volume", type=float, default=DEFAULT_MIN_VOLUME)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)


def main():
    p = argparse.ArgumentParser(description="Discover Polymarket markets")
    sub = p.add_subparsers(dest="cmd")
    d = sub.add_parser("discover")
    _add_filter_args(d)
    sc = sub.add_parser("scan")
    _add_filter_args(sc)
    args = p.parse_args()
    cats = [c.strip() for c in (args.categories or "").split(",")]

    if args.cmd == "discover":
        markets = discover(cats, args.min_liquidity, args.min_volume, args.limit)
        for m in markets:
            prices = json.loads(m["outcome_prices"]) if isinstance(m["outcome_prices"], str) else m["outcome_prices"]
            yes_p = f"{float(prices[0])*100:.1f}%" if prices and len(prices) > 0 else "?"
            print(f"[{m['category']}:{m['category_confidence']}] "
                  f"{m['question'][:70]}  Yes:{yes_p}  Vol:{_fmt_volume(m['volume_usd'])}")
        print(f"\nTotal: {len(markets)} markets")

    elif args.cmd == "scan":
        result = run_scan(cats, args.min_liquidity, args.min_volume, args.limit)
        print(f"Scan #{result['scan_id']}: {result['n_markets']} markets")
        for cat, n in result["by_category"].items():
            print(f"  {cat}: {n}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
