#!/usr/bin/env python3
"""Publish polymarket-signals dashboard to Cloudflare Pages.

Orchestrates: generate_dashboard.py → wrangler pages deploy → result.
All failures alert Telegram. Token from env only (never CLI arg).

Usage:
    python3 publish_dashboard.py [--dry-run]

Environment (required):
    CLOUDFLARE_API_TOKEN     — scoped to Pages:Edit on one project
    CLOUDFLARE_ACCOUNT_ID    — Cloudflare account ID
    DASHBOARD_CF_PROJECT     — Pages project name (default: polymarket-signals-dashboard)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
WRANGLER_PIN = "4"  # major version pin

# Telegram alert settings (reuse skill's delivery)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram(message: str) -> None:
    """Send alert to Telegram via bot API. Best-effort, never raises."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("WARNING: Telegram credentials not set, skipping alert", file=sys.stderr)
        return
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = f"chat_id={TELEGRAM_CHAT_ID}&text={message}".encode("utf-8")
        req = urllib.request.Request(url, data=payload)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"WARNING: Telegram send failed: {e}", file=sys.stderr)


def _alert_failure(step: str, error: str) -> None:
    """Send Telegram alert on publish failure (C4)."""
    msg = f"🚨 Dashboard publish FAILED at '{step}': {error[:500]}"
    _send_telegram(msg)


def preflight() -> None:
    """Check prerequisites. Exit + alert on failure."""
    # Check wrangler
    try:
        result = subprocess.run(
            ["wrangler", "--version"], capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            raise RuntimeError(f"wrangler not found or broken: {result.stderr.strip()}")
    except FileNotFoundError:
        raise RuntimeError("wrangler not found in PATH — install: npm i -g wrangler")

    # Check env vars
    missing = []
    for var in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)} — set in ~/.hermes/hermes.env")


def run_generate() -> Path:
    """Run generate_dashboard.py as subprocess. Returns output path."""
    gen_script = SCRIPTS_DIR / "generate_dashboard.py"
    if not gen_script.exists():
        raise FileNotFoundError(f"generate_dashboard.py not found at {gen_script}")

    result = subprocess.run(
        [sys.executable, str(gen_script)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    # Parse output path from the first line
    first_line = result.stdout.strip().split("\n")[0]
    if first_line.startswith("Dashboard generated:"):
        out_path = Path(first_line.split(":", 1)[1].strip())
        if not out_path.exists():
            raise RuntimeError(f"Generated file not found: {out_path}")
        return out_path

    raise RuntimeError(f"Unexpected generate output: {result.stdout[:200]}")


def wrangler_deploy(dist_dir: Path, project: str, dry_run: bool = False) -> str:
    """Deploy dist/ via wrangler pages deploy. Returns deployment URL."""
    cmd = ["wrangler", "pages", "deploy", str(dist_dir), "--project-name", project]
    if dry_run:
        cmd.append("--dry-run")

    env = os.environ.copy()
    # Ensure token is in env for wrangler (never as CLI arg — C8)
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "wrangler deploy failed")

    stdout = result.stdout.strip()
    return stdout


def main(dry_run: bool = False) -> None:
    """Full publish pipeline: preflight → generate → deploy."""
    project = os.environ.get("DASHBOARD_CF_PROJECT", "polymarket-signals-dashboard")

    # 1. Preflight
    try:
        preflight()
    except RuntimeError as e:
        _alert_failure("preflight", str(e))
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Generate dashboard
    try:
        dist_path = run_generate()
        print(f"Generated: {dist_path}")
    except Exception as e:
        _alert_failure("generate", str(e))
        print(f"ERROR: generate failed: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Deploy via wrangler
    dist_dir = dist_path.parent
    try:
        output = wrangler_deploy(dist_dir, project, dry_run=dry_run)
        print(f"Deploy {'(dry-run) ' if dry_run else ''}output:\n{output}")
    except Exception as e:
        _alert_failure("deploy", str(e))
        print(f"ERROR: deploy failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Success
    public_url = os.environ.get("DASHBOARD_PUBLIC_URL", f"https://{project}.pages.dev")
    print(f"\nDashboard published at: {public_url}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Publish dashboard to Cloudflare Pages")
    p.add_argument("--dry-run", action="store_true", help="Validate upload without publishing")
    args = p.parse_args()

    try:
        main(dry_run=args.dry_run)
    except Exception as e:
        _alert_failure("unknown", str(e))
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
