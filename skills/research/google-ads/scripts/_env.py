#!/usr/bin/env python3
"""Load google-ads.env into os.environ (no external dep).

google-ads-python's `load_from_env()` reads GOOGLE_ADS_* vars from os.environ.
This helper parses the google-ads.env file (KEY=VALUE lines) into os.environ so
scripts work when run directly (no shell `source` required) — fixes M1: monitor
used load_from_storage() (google-ads.yaml) while deploy used load_from_env()
(env vars); now both share one cred path (google-ads.env).
"""
import os
from pathlib import Path

DEFAULT_ENV_PATH = Path(__file__).parent.parent / "google-ads.env"


def load_google_ads_env(env_path: str | Path | None = None) -> bool:
    """Parse google-ads.env (KEY=VALUE) into os.environ. Returns True if loaded.

    Uses os.environ.setdefault so real environment variables (e.g. set by Hermes
    cron) always win over the file — the file is a convenience default.
    """
    p = Path(env_path) if env_path else DEFAULT_ENV_PATH
    if not p.exists():
        return False
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        # Strip inline comments + respect quotes (fixes C1: the .env.example uses
        # `KEY=value  # comment` which naive .strip() kept, corrupting customer_id
        # etc.). Quoted value → keep inner content; unquoted → cut at first #.
        if val and val[0] in "\"'":
            q = val[0]
            end = val.find(q, 1)
            val = val[1:end] if end > 0 else val[1:]
        else:
            val = val.split("#", 1)[0]
        val = val.strip()
        if val:
            os.environ.setdefault(key, val)
    return True
