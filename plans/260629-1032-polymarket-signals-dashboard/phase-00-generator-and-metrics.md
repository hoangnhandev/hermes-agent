# Phase 00 — Generator Core + Metrics

## Context
- Parent: [plan.md](plan.md). Scenario criticals: C5, C6, C7.
- Reads: `skills/research/polymarket-signals/scripts/_schema.py`, `_store_reads.py`, `_paths.py`, `_store_core.py`.

## Overview
Build the data layer of the dashboard: a stdlib-only Python module that opens a
**read-only** SQLite connection and computes all dashboard metrics into a plain
dict. No HTML here (phase-01). Must be safe under concurrent scan writes.

## Key Insights
- `_store_core._r()` takes `flock LOCK_EX|LOCK_NB` and **`sys.exit(1)` on contention**.
  Generator MUST NOT use it — it would die whenever a scan is mid-write.
- DB runs in **WAL mode** (`PRAGMA journal_mode=WAL` in `_store_core._connect()`).
  WAL allows concurrent readers + 1 writer with no lock. A `mode=ro` URI connection
  gets a consistent snapshot without blocking/killing the writer. → Use this.
- `_store_reads.get_predictions(resolved_only=True)` already JOINs outcomes. Reuse for
  resolved set; call again with `resolved_only=False` for pending/active signals.

## Requirements
- **Functional**: compute (1) per-category calibration bins, (2) per-category + overall
  Brier, (3) edge distribution, (4) active signals, (5) recent predictions, (6) resolution
  health, (7) header stats + last scan.
- **Non-functional**: read-only (no commit), never `sys.exit` on lock, <200 lines/file,
  stdlib only, no new pip dep.

## Architecture
```
scripts/_dashboard_data.py   # read-only conn + metric computation → dict
  ├─ open_ro(db_path)        # sqlite3.connect("file:...?mode=ro", uri=True, ...)
  ├─ only_done_scans(conn)   # filter scans.status='done' (scenario #8)
  ├─ dedup_latest(rows)      # per condition_id keep latest scan prediction (F-03)
  ├─ calibration(resolved)   # bin predicted_p → freq(outcome_int==1), n per bin
  ├─ brier(resolved)         # mean (predicted_p - outcome_int)^2 ; per cat + overall
  ├─ edge_dist(all_preds)    # predicted_p - market_p ; skip NULL market_p
  ├─ active_signals(pending) # |edge|>thr, sorted desc
  └─ build_metrics()         # orchestrates → dict for renderer
```

## Related Code Files
- **Create**: `skills/research/polymarket-signals/scripts/_dashboard_data.py`
- **Read (reuse)**: `_store_reads.py` (query patterns), `_paths.get_db_path()`
- **Do NOT import** `_store_core` (locking/exit semantics unsafe for read-only snapshot).

## Implementation Steps
1. `open_ro(db_path)`: `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)`,
   `row_factory=Row`. Wrap connect in try/except `OperationalError` (DB missing/locked) →
   return empty metrics (do NOT exit). Set `PRAGMA query_only=1` as belt-and-suspenders.
2. Query resolved predictions joining `scans` filtered `scans.status='done'` (so an
   in-progress scan's partial data is excluded). De-dup by `condition_id` (max scan_id).
3. **Brier**: `mean((predicted_p - outcome_int)**2)` over rows where `outcome_int IN (0,1)`
   (exclude NULL/disputed, scenario #35). Per category + overall. None if 0 resolved.
4. **Calibration**: fixed bins `[0,.1,.2,...,1.0]`; per bin `n` + `freq=outcome_int.mean()`.
   Skip bins with `n==0`. Return list of `{bin_lo, bin_hi, n, freq}`.
5. **Edge**: `predicted_p - market_p`; skip rows with NULL `market_p` (scenario #4).
   Histogram counts + list of top |edge| active signals (pending only, threshold from env
   or const).
6. **Resolution health**: count `resolved`/`pending`/`disputed` (from `resolution_status`).
7. **Header stats**: total predictions, resolved, pending, last scan `ts`, mean Brier
   (None→"collecting"). Wrap every metric so **empty DB → all-None/zero, no exception**.
8. `build_metrics()` returns a single dict; unit-testable with a temp SQLite fixture.

## Todo
- [ ] `open_ro()` read-only WAL conn, no-exit on lock
- [ ] done-scan filter + dedup-latest (F-03)
- [ ] Brier resolved-only (C5)
- [ ] Calibration bins with n
- [ ] Edge dist + active signals
- [ ] Resolution health + header stats
- [ ] Empty-DB fixture returns valid empty metrics (C6)
- [ ] Smoke run against live `~/.hermes/polymarket_signals.db`

## Success Criteria
- `python3 _dashboard_data.py` (CLI debug print) emits valid metrics dict from live DB.
- Empty DB → dict with `resolved_count=0`, `brier=None`, no traceback.
- Running while a scan writes → no `database is locked` exit (snapshot read succeeds).
- File <200 lines, stdlib only.

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| WAL not active → reader blocks | Med | `_connect()` already sets WAL; `mode=ro` still snapshots. Verify `journal_mode` |
| De-dup ambiguity (which prediction) | Med | Document: latest scan_id per condition_id |
| Disputed outcome miscounted | High | Exclude `outcome_int NOT IN (0,1)` from Brier (scenario #35) |

## Security
- `query_only=1` + `mode=ro` → impossible to write even if a bug exists.
- No secrets read; no network.

## Next Steps
- → phase-01: render this dict into the HTML template + 7 Plotly panels.
