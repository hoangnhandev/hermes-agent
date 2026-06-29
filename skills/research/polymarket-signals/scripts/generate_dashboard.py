#!/usr/bin/env python3
"""Generate static dashboard HTML from polymarket-signals SQLite.

Orchestrates: build_metrics() → build_html() → atomic write to dist/.

Usage:
    python3 generate_dashboard.py [--out PATH]
"""

import argparse
import os
import sys
from pathlib import Path

from _dashboard_data import build_metrics
from _dashboard_render import build_html

SCRIPTS_DIR = Path(__file__).parent
DEFAULT_OUT = SCRIPTS_DIR.parent / "dashboard" / "dist" / "index.html"
MAX_HTML_SIZE = 2 * 1024 * 1024  # 2MB sanity cap


def generate(out_path: Path | str | None = None) -> Path:
    """Generate dashboard HTML, write atomically. Returns output path."""
    if out_path is None:
        out_path = DEFAULT_OUT
    out_path = Path(out_path)

    # Build metrics (read-only, safe under concurrent scan writes)
    metrics = build_metrics()

    # Render HTML
    html_content = build_html(metrics)

    # Sanity check size
    size = len(html_content.encode("utf-8"))
    if size > MAX_HTML_SIZE:
        print(f"WARNING: dashboard HTML is {size:,} bytes (cap {MAX_HTML_SIZE:,})", file=sys.stderr)

    # Atomic write: temp → os.replace (never serve half-written file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".html.tmp")
    try:
        tmp_path.write_text(html_content, encoding="utf-8")
        os.replace(str(tmp_path), str(out_path))
    except OSError as e:
        # Clean up temp file on failure
        tmp_path.unlink(missing_ok=True)
        raise

    # Print summary
    total = metrics.get("total_predictions", 0)
    resolved = metrics.get("resolved_count", 0)
    brier = metrics.get("mean_brier")
    print(f"Dashboard generated: {out_path}")
    print(f"  Predictions: {total} total, {resolved} resolved")
    print(f"  Brier: {brier:.4f}" if brier is not None else "  Brier: collecting")
    print(f"  Size: {size:,} bytes")

    return out_path


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate polymarket-signals dashboard")
    p.add_argument("--out", type=str, default=None, help="Output HTML path")
    args = p.parse_args()
    try:
        generate(args.out)
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
