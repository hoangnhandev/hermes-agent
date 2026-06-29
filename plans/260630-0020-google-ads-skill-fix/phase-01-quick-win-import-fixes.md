# Phase 01 — Quick-Win Import / Crash Fixes

## Context Links
- Plan: [`plan.md`](plan.md)
- Findings: C1 (`_store.py:594` `timedelta` NameError), C4 (`sync_to_d1.py:251` `import argparse` after `main()`)

## Overview
- **Priority**: P1 (blocker)
- **Status**: pending
- **Effort**: 1h
- Two one-line import fixes that prevent monitor crash and standalone sync crash.

## Key Insights
- C1: `_store.py` imports `from datetime import datetime` only; line 594 uses `timedelta` → `NameError` when anomaly baseline computed. Monitor anomaly path is therefore dead.
- C4: `sync_to_d1.py` calls `argparse` in `main()` but `import argparse` is at line 252 (after `main()` def, only runs under `__main__`). Standalone `python3 sync_to_d1.py` → `NameError`. Cron invocation breaks.

## Requirements
### Functional
- `_store.py` must import `timedelta`.
- `sync_to_d1.py` must import `argparse` at module top.
### Non-functional
- No behavior change beyond unblocking execution.

## Architecture
N/A — pure import additions.

## Interfaces
**Consumes:** none.
**Produces (signatures unchanged):**
- `_store.get_baseline_metrics(conn, campaign_id, days=7) -> dict` (now executes instead of crashing)
- `sync_to_d1.main() -> int` (now runs standalone)

## Related Code Files
- **Modify**: `skills/research/google-ads/scripts/_store.py` (line 6)
- **Modify**: `skills/research/google-ads/scripts/sync_to_d1.py` (line 14 imports, remove line 252)

## Implementation Steps
1. `_store.py` line 6: `from datetime import datetime` → `from datetime import datetime, timedelta`
2. `sync_to_d1.py`: add `import argparse` to top import block (after line 14 `from datetime import datetime`); delete `import argparse` at line 252.
3. Smoke-test both modules import cleanly.

## Todo List
- [ ] Fix `_store.py` timedelta import
- [ ] Fix `sync_to_d1.py` argparse import
- [ ] `python3 -c "import _store, sync_to_d1"` clean

## Success Criteria
- `python3 -c "from _store import get_baseline_metrics"` succeeds.
- `python3 sync_to_d1.py --help` prints help (no NameError).
- `python3 monitor.py --mode detect` no longer crashes on baseline calc.

## Risk Assessment
- **Low**. One-line edits, mechanical. Risk = editing wrong line; mitigated by grep verification.

## Security Considerations
None.

## Next Steps
- Unblocks phases 02, 06, 07, 08 (all touch `_store.py`/`sync_to_d1.py`).
