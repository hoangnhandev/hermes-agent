# Phase 08 — Refactor: Split Oversized Files + DRY

## Context Links
- Plan: [`plan.md`](plan.md)
- Finding: M4 (`_store.py` 694 lines, `monitor.py` 515 lines exceed <200 guideline; `init_campaigns_db.py` duplicates `_store.py` ~80%)

## Overview
- **Priority**: P3 (tech-debt / maintainability)
- **Status**: pending
- **Effort**: 4h
- Split `_store.py` into focused modules; delete `init_campaigns_db.py` (duplicate); trim `monitor.py` via extraction.

## Key Insights
- `_store.py` (694 lines) mixes 3 concerns: (a) campaigns CRUD, (b) metrics storage, (c) anomaly baseline/detection. Split into 3 files by concern.
- `init_campaigns_db.py` (373 lines) reimplements `create_tables` from `_store.py` — DRY violation. One init path: `_store.py init` (already documented in SKILL.md quickstart). Delete the standalone script.
- `monitor.py` (515 lines): extract GAQL query building + anomaly detection into helpers.
- **Order matters**: run AFTER phases that modify `_store.py` (01, 06) to avoid merge churn. Phase 07 may also touch monitor.py — coordinate (Phase 07 owns monitor.py logic; Phase 08 owns the *split*, so sequence 07→08).

## Requirements
### Functional
- No behavior change — pure refactor. All existing function signatures preserved (re-exported from `_store.py` for backwards compat).
- Every `.py` in `scripts/` <200 lines.
### Non-functional
- `_store.py` re-exports split-module symbols so `from _store import X` still works (no churn in callers).

## Architecture
```
scripts/
  _store.py            (<200) campaigns CRUD + re-exports
  _store_metrics.py    (<200) daily_metrics write/read
  _store_anomaly.py    (<200) baseline + anomaly detection
  monitor.py           (<200) orchestrator only
  _monitor_queries.py  (<200) GAQL builders + API fetch
  (deleted) init_campaigns_db.py
```

## Interfaces
**Consumes:** none new.
**Produces:** same public API (re-exports):
- `_store.py`: `from _store_metrics import *` + `from _store_anomaly import *` (or explicit re-exports) so `from _store import get_baseline_metrics, save_metrics` unchanged.

## Related Code Files
- **Modify**: `scripts/_store.py` (trim + re-export)
- **Create**: `scripts/_store_metrics.py`, `scripts/_store_anomaly.py`, `scripts/_monitor_queries.py`
- **Modify**: `scripts/monitor.py` (trim, import from `_monitor_queries`)
- **Delete**: `scripts/init_campaigns_db.py`
- **Read-only**: all callers (creator.py, deploy.py, sync_to_d1.py, daily_report.py)

## Implementation Steps
1. Extract `_store_metrics.py`: `save_metrics`, `get_metrics`, `get_unsynced_metrics`-adjacent reads.
2. Extract `_store_anomaly.py`: `get_baseline_metrics`, anomaly rule functions.
3. `_store.py`: keep campaigns CRUD + init_db + `from _store_metrics import *` etc. Verify <200 lines.
4. Extract `_monitor_queries.py`: GAQL query strings + fetch helpers.
5. `monitor.py`: import from `_monitor_queries`; trim to orchestrator.
6. Delete `init_campaigns_db.py`; grep for references (cron, docs) → point to `_store.py init`.
7. Smoke-test: `python3 -c "from _store import get_baseline_metrics, save_metrics, init_db"` + run monitor full cycle.

## Todo List
- [ ] Split _store.py → _store_metrics.py + _store_anomaly.py
- [ ] Re-exports in _store.py
- [ ] Extract _monitor_queries.py from monitor.py
- [ ] Delete init_campaigns_db.py + fix references
- [ ] Verify all files <200 lines (`wc -l`)
- [ ] Full smoke test (monitor full cycle, creator, sync)

## Success Criteria
- `wc -l scripts/*.py` — every file ≤200 lines.
- `python3 _store.py init` still works (single init path).
- `init_campaigns_db.py` gone; no dangling references.
- Monitor + creator + sync all run unchanged end-to-end.

## Risk Assessment
- **Medium** — refactor introduces import cycles or breaks callers. **Mitigation**: re-exports preserve API; run full smoke test; do AFTER all logic phases (01,06,07) land.
- **Low** — hidden dynamic references to init_campaigns_db.py. **Mitigation**: grep repo + crontab.

## Security Considerations
None (pure structural refactor).

## Next Steps
- Depends on Phases 01, 06, 07 (run last among code phases). Phase 09 verifies + updates docs.
