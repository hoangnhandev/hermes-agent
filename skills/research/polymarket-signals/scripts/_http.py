#!/usr/bin/env python3
"""Shared HTTP helpers for polymarket-signals clients.

Reused from sibling polymarket skill patterns. stdlib-only (urllib).
"""

import json
import sys
import urllib.error
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"

HEADERS = {"User-Agent": "hermes-agent/1.0"}


def _get(url: str, timeout: int = 15) -> dict | list:
    """GET request, return parsed JSON. Exits on HTTP/network error."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.reason} — {url}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason} — {url}", file=sys.stderr)
        sys.exit(1)


def _get_safe(url: str, timeout: int = 15) -> dict | list | None:
    """GET request, return parsed JSON or None on error (non-fatal)."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, Exception):
        return None


def _parse_json_field(val):
    """Parse double-encoded JSON fields (outcomePrices, outcomes, clobTokenIds)."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


def _fmt_pct(price) -> str:
    """Format price as percentage string."""
    try:
        return f"{float(price) * 100:.1f}%"
    except (ValueError, TypeError):
        return str(price)


def _fmt_volume(vol) -> str:
    """Format volume as human-readable string."""
    try:
        v = float(vol)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:.0f}"
    except (ValueError, TypeError):
        return str(vol)


def _build_gamma_url(path: str, params: dict = None) -> str:
    """Build a Gamma API URL with optional query params."""
    from urllib.parse import urlencode
    base = f"{GAMMA}{path}"
    if params:
        qs = urlencode({k: v for k, v in params.items() if v is not None})
        if qs:
            base += f"?{qs}"
    return base
