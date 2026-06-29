# Phase 00 — Setup, Scaffold, SQLite Store

## Context Links

- Design: `plans/20260626-polymarket-signal-bot-brainstorm.md` (§3 architecture, §4 components, §5 phasing row 0).
- Overview: `plans/20260626-polymarket-signal-bot/plan.md`.
- Reuse pattern: `skills/research/polymarket/SKILL.md` + `skills/research/polymarket/scripts/polymarket.py`.
- Hermes conventions: `AGENTS.md` (skills, get_hermes_home, prompt caching, footprint ladder).

## Overview

- **Priority**: P2 · **Status**: COMPLETE · **Effort**: 5h
- Stand up the new skill directory, the SKILL.md procedure, the SQLite tracking
  store with full schema, config/.env var definitions, and references scaffolding.
- No data fetching or LLM yet — this phase only creates the skeleton every later phase fills.

## Key Insights

- The store is the **spine** of the whole calibration system; its schema must be
  right before any data flows. Get the prediction/outcome/category tables correct now.
- Use `get_hermes_home()` for the db path so Hermes profiles stay isolated. Never
  hardcode `~/.hermes`.
- SKILL.md `description` MUST be ≤60 chars, one sentence, ends with `.` (Hermes hardline rule).

## Requirements

**Functional**
- Skill discoverable by Hermes skill loader (correct frontmatter + dir layout).
- `store.py` exposes idempotent `init_db()` + CRUD: insert prediction, insert
  market metadata, mark outcome, read by category/status.
- DB auto-created on first run at the profile-aware path.

**Non-functional**
- All scripts stdlib-only (sqlite3, json, argparse, os, pathlib). No pip deps.
- Each file <200 lines.
- No network calls in this phase.

## Architecture

```
skills/research/polymarket-signals/
├── SKILL.md                      # procedure for the agent
├── scripts/
│   ├── store.py                  # SQLite schema + CRUD (THIS PHASE)
│   └── _paths.py                 # get_hermes_home() db path helper (THIS PHASE)
├── references/
│   ├── api-endpoints.md          # stub — filled phase 01 (link to sibling skill)
│   └── calibration.md            # stub — filled phase 04/05
└── templates/
    └── env.example.md            # documents required .env vars
```

DB schema (`~/.hermes/polymarket_signals.db`):

```
markets(condition_id TEXT PRIMARY KEY, slug TEXT, question TEXT, category TEXT,
        category_override TEXT,           -- <!-- RED-TEAM F-10 --> manual override (NULL = derived)
        category_confidence REAL,         -- <!-- RED-TEAM F-10 --> 1.0 single-tag; <1.0 ambiguous/quarantine
        clob_token_ids TEXT, outcome_prices TEXT, volume_usd REAL,
        end_date TEXT, source_first_seen TEXT)

predictions(id INTEGER PRIMARY KEY AUTOINCREMENT, condition_id TEXT,
            scan_id INTEGER,              -- <!-- RED-TEAM F-03 --> FK scans.id; derived BEFORE any LLM call
            status TEXT,                  -- <!-- RED-TEAM F-04 --> 'pending'|'done'|'error'
            predicted_p REAL, market_p REAL, confidence REAL,
            sources TEXT,          -- JSON array: ["llm","manifold","metaculus",...]
            rationale TEXT,        -- LLM reasoning, kept short
            category TEXT, scan_ts TEXT,  -- ISO8601 UTC
            ensemble_breakdown TEXT,-- JSON: per-source P (added phase 03)
            UNIQUE(condition_id, scan_id),-- <!-- RED-TEAM F-03 --> idempotency: one pred per market per scan
            FOREIGN KEY(condition_id) REFERENCES markets(condition_id),
            FOREIGN KEY(scan_id) REFERENCES scans(id))

outcomes(condition_id TEXT PRIMARY KEY, outcome_int INTEGER, -- 1/0 yes-resolved
         resolved_ts TEXT, resolution_source TEXT,
         outcome_confidence REAL,         -- <!-- RED-TEAM F-06 --> UMA-finalized=1.0; <1.0 if disputed/ambiguous
         outcome_raw TEXT,                -- <!-- RED-TEAM F-06 --> raw Gamma payload (audit/forensics)
         resolution_status TEXT,          -- <!-- RED-TEAM F-06 --> ENUM('resolved','void','disputed','ambiguous')
         previous_outcome_int INTEGER)    -- <!-- RED-TEAM F-06 --> audit: prior value on re-resolution (mark_outcome idempotent)

scans(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, n_markets INTEGER,
      categories TEXT, cost_note TEXT,    -- <!-- RED-TEAM F-11 --> est. tokens/$ per scan
      status TEXT)                        -- <!-- RED-TEAM F-04 --> scan row created at START ('running'->'done'/'error')

schema_meta(key TEXT PRIMARY KEY, value TEXT)  -- <!-- RED-TEAM F-12 --> holds 'schema_version', writer identity, etc.
```

Indexes: `predictions(category)`, `predictions(condition_id)`,
`predictions(scan_ts)`, `markets(category)`. <!-- RED-TEAM F-03 --> Add `predictions(scan_id)`.

### Store Hardening / Operational Contract <!-- RED-TEAM F-05, F-12 -->

- **Concurrency (F-05)**: Hermes cron (`scheduler.run_job`) runs in thread pools with process-global env vars; `run_scan` and `resolve_check` touch the SAME sqlite file → `database is locked`. EVERY connection MUST open with `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA synchronous=NORMAL;`. Add a **process-wide `fcntl.flock`** on a lockfile (e.g. `~/.hermes/polymarket_signals.db.lock`) to serialize `run_scan` vs `resolve_check`. **Thread-safety contract:** the store is safe to open from independent cron jobs only via the flock + WAL; do not assume single-process isolation.
- **Migrations + backup + integrity (F-12)**: `schema_meta('schema_version')` tracks version. A versioned `migrate(from_v→to_v)` chain runs on every `init_db()` — **define ALL migrations now, even for deferred features** (forward-only, never destructive). Daily cron: `VACUUM INTO ~/.hermes/polymarket_signals.db.bak.{date}`. Run `PRAGMA integrity_check` on open; fail loud if non-OK. `chmod 0600` the DB at init.
- **Optional, lower priority (F-12)**: HMAC over `calibration_state` rows + append-only `audit_log(writer, ts, action, payload)` — any plugin under `~/.hermes` could otherwise tamper calibration. Defer until multi-plugin concern is real.

## Interfaces

**Consumes**: none (foundation).
**Produces** (exact signatures `scripts/store.py` must expose — later phases verify against):
- `get_db_path() -> pathlib.Path`
- `init_db() -> None`  <!-- RED-TEAM F-12 --> runs `migrate()` chain + integrity_check + chmod 0600
- `upsert_market(condition_id, slug, question, category, clob_token_ids, outcome_prices, volume_usd, end_date, source_first_seen, category_confidence=1.0) -> None`  <!-- RED-TEAM F-10 --> stores derived + confidence
- `create_scan(ts, status='running') -> int`  <!-- RED-TEAM F-03, F-04 --> FIRST action of a scan; returns scan_id BEFORE any LLM call
- `insert_prediction(condition_id, scan_id, status='pending', **fields) -> int`  <!-- RED-TEAM F-03, F-04 --> `UNIQUE(condition_id, scan_id)` enforced; use `INSERT OR IGNORE`; `status='pending'` row created pre-LLM
- `update_prediction(pred_id, status='done', predicted_p, market_p, confidence, sources, rationale, category) -> None`  <!-- RED-TEAM F-04 --> flips pending→done after LLM call
- `set_ensemble_breakdown(pred_id, breakdown:dict) -> None`  (used from phase 03)
- `mark_outcome(condition_id, outcome_int, resolved_ts, resolution_source, outcome_confidence, outcome_raw, resolution_status) -> None`  <!-- RED-TEAM F-06 --> idempotent; archives prior into `previous_outcome_int`; rejects non-binary/void/disputed (quarantine out of scoring)
- `get_predictions(category=None, resolved_only=False, limit=None) -> list[dict]`
- `get_pending_resolution(limit=None) -> list[dict]`  (markets with predictions but no outcome)
- `finish_scan(scan_id, n_markets, categories:list, cost_note='', status='done') -> None`  <!-- RED-TEAM F-03, F-04 --> was `log_scan`; called at scan END
- `recategorize(condition_id, category) -> None`  <!-- RED-TEAM F-10 --> CLI: `store.py recategorize <condition_id> <category>`; sets `category_override` (no migration needed)
- `migrate(from_v:int, to_v:int) -> None`  <!-- RED-TEAM F-12 --> versioned schema migration chain

## Related Code Files

**Create** (all under `skills/research/polymarket-signals/`):
- `SKILL.md`
- `scripts/store.py`
- `scripts/_paths.py`
- `references/api-endpoints.md` (stub)
- `references/calibration.md` (stub)
- `templates/env.example.md`

**Modify**: none.
**Delete**: none.
**Core edits**: NONE (skill-only).

## Implementation Steps

1. Create dir tree (`scripts/`, `references/`, `templates/`).
2. Write `SKILL.md` with frontmatter: `name: polymarket-signals`,
   `description:` ≤60 chars ending `.`, `version: 0.1.0`, `platforms: [linux, macos, windows]`.
   Body sections (modern order): `# Polymarket Signals Skill`, 2-3 sentence intro,
   `## When to Use`, `## Prerequisites`, `## How to Run`, `## Quick Reference`,
   `## Procedure` (high-level; detailed in later phases), `## Pitfalls`,
   `## Verification`. Reference sibling `polymarket` skill for raw endpoint details.
3. Write `scripts/_paths.py`: import `get_hermes_home` from `hermes_constants`;
   `get_db_path()` returns `get_hermes_home() / "polymarket_signals.db"`.
   Wrap import in try/except fallback to `Path.home()/".hermes"` only if Hermes
   internals unavailable (skill must still run standalone via terminal).
4. Write `scripts/store.py` with the schema + CRUD in **Interfaces**. `init_db()`
   creates all tables IF NOT EXISTS + indexes. Use parameterized queries throughout
   (SQL-injection safe). Add `if __name__ == "__main__"` argparse driver:
   `init`, `dump-predictions [--category C] [--limit N]`, `stats`.
5. Write `templates/env.example.md` documenting (all OPTIONAL unless noted):
   `MANIFOLD_API_KEY` (free, anon ok), `METACULUS_API_KEY` (free),
   `COINGECKO_API_KEY` (free tier, optional demo key), `TELEGRAM_CHAT_ID`
   (for gateway wiring). State clearly: NO Polymarket trading key is ever needed.
6. Stub `references/api-endpoints.md` with a link to
   `../polymarket/references/api-endpoints.md` + TODO placeholders per later phase.
7. Stub `references/calibration.md` with the Brier/calibration-curve/gating
   definitions copied from brainstorm §6 as section headers (filled later).

## Todo List

- [ ] Dir tree created
- [ ] SKILL.md passes the ≤60-char description assert
- [ ] `store.py` `init_db()` creates all 4 tables + indexes idempotently
- [ ] CRUD signatures match **Interfaces** exactly
- [ ] `python3 scripts/store.py init` works against a temp HERMES_HOME
- [ ] `env.example.md` lists optional keys, explicitly states NO trade key

## Success Criteria

- Skill dir present with correct frontmatter; Hermes skill loader finds it.
- `init_db()` is idempotent; running twice raises no error.
- A prediction can be inserted and read back by category (manual smoke test).
- Zero core files touched (`git diff --stat` shows only the new skill dir).
- Each new file <200 lines.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Schema missing a column a later phase needs → migration pain | Med | High | Schema reviewed against ALL phases now; `ensemble_breakdown`, `sources`, `confidence`, `category` all present up front. |
| Hardcoded `~/.hermes` breaks profiles | Med | High | `_paths.get_db_path()` uses `get_hermes_home()`; smoke test sets a temp HERMES_HOME. |
| SKILL.md description >60 chars rejected | Low | Med | Run the regex assert in Implementation Step 2 before marking done. |

## Security Considerations

- DB holds no secrets. `.env` template documents keys as OPTIONAL and never a trade key.
- Parameterized SQL everywhere (no f-string SQL).
- No network in this phase — nothing to exfiltrate.

## Next Steps

- Unblocks **Phase 01** (data clients call `upsert_market` + `log_scan`).
- Calibrated gating (Phase 04) depends on the `outcomes` + `predictions(category)` schema defined here.
