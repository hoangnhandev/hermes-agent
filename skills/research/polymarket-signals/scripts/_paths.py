#!/usr/bin/env python3
"""Path helpers for polymarket-signals skill.

Provides the profile-aware SQLite database path using Hermes home.
Falls back to ~/.hermes when run outside Hermes (standalone).
"""

import os
from pathlib import Path


def get_db_path() -> Path:
    """Return the SQLite DB path, respecting HERMES_HOME.

    Uses Hermes get_hermes_home() when importable (inside Hermes runtime),
    falls back to HERMES_HOME env var or ~/.hermes otherwise.
    """
    # Try importing from Hermes runtime first
    try:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
        return home / "polymarket_signals.db"
    except ImportError:
        pass

    # Fallback: env var or default
    home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    return Path(home) / "polymarket_signals.db"


def get_db_lock_path() -> Path:
    """Return the flock lockfile path for DB concurrency serialization."""
    return get_db_path().with_suffix(".db.lock")
