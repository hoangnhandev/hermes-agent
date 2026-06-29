# Phase 01 — Data Clients (markets, prices, resolution)

## Context Links

- Design: `plans/20260626-polymarket-signal-bot-brainstorm.md` (§3 data layer, §4 markets/prices clients).
- Overview: `plans/20260626-polymarket-signal-bot/plan.md`.
- Reuse: `skills/research/polymarket/scripts/polymarket.py` (match its `_get`/`_parse_json_field` style) and
  `skills/research/polymarket/references/api-endpoints.md` (Gamma/CLOB/Data base URLs + rate limits).
- Depends on: `phase-00-setup-scaffold-store.md` (store CRUD signatures).

## Overview

- **Priority**: P2 · **Status**: COMPLETE · **Effort**: 5h
- Three stdlib HTTP clients: discover+filter Crypto/Politics markets, fetch live
  price+history, fetch resolved markets+outcomes. All write into the Phase 00 store.
- Still no LLM. Goal: a cron-runnable scan that logs the market universe to SQLite.

### Prerequisite Verification (BLOCKER) <!-- RED-TEAM F-02 -->

Polymarket migrated to **CLOB V2 on 2026-04-28**; V1 endpoints (`/midpoint`, `/spread`, synthetic `/prices-history`) are gone/broken. The sibling skill was V1. **Before writing any client code, probe LIVE:**
1. Hit the V1 endpoints above and the V2 equivalents — record which respond 200 with sane bodies vs 410/404.
2. Pin the **V2 base URL + endpoint shapes** (e.g. book/prices endpoints) in `references/api-endpoints.md`.
3. Add a **price-sanity assertion** before any prediction is logged: `0 < yes_price < 1` AND `mid` within `[bid, ask]`. Fail loud otherwise.
**Do NOT blindly copy sibling V1 patterns.** They are reference, not source of truth.

## Key Insights

- Gamma returns `outcomePrices`/`outcomes`/`clobTokenIds` as **double-encoded JSON
  strings** — reuse the sibling skill's `_parse_json_field` helper, do not rewrite parsing.
- Filter early at the API (liquidity/volume/active) to bound cost — prompt-cache + LLM cost
  scale with market count. This is the YAGNI cost-control lever.
- Category tagging (crypto vs politics) drives the whole calibration loop — derive it
  deterministically from Gamma tags/event slug, with a manual override path.

## Requirements

**Functional**
- `markets_client.py`: discover active markets, filter to Crypto+Politics by min
  liquidity and min volume, tag category, upsert into `markets` table.
- `prices_client.py`: given a condition_id/clob_token_id, return current Yes price
  (mid) + optional N-point history; writes nothing (pure fetch, called by predictor).
- `resolution_client.py`: find markets that closed since last scan, fetch outcome,
  call `store.mark_outcome(...)`.
- A `scan` subcommand orchestrates markets_client → store, then `log_scan`.

**Non-functional**
- stdlib-only (urllib, json, argparse, urllib.parse). No `requests`.
- Every HTTP call has a timeout (≤15s, matching sibling skill) + `User-Agent: hermes-agent/1.0`.
- Each client <200 lines; one responsibility each (DRY).

## Architecture

```
cron tick
   └─ markets_client.py discover --categories crypto,politics \
        --min-liquidity 5000 --min-volume 10000
        → GET gamma /markets (or /events) filtered
        → upsert_market(...) per market
        → log_scan(ts, n, categories)
   (separate cron, lower freq)
   └─ resolution_client.py check
        → GET gamma /markets closed=true since=last_scan
        → for each: fetch resolution; store.mark_outcome(...)
prices_client.py is a LIBRARY called by predict.py (phase 02) — CLI driver for debugging.
```

Filter rules (defaults, overridable via flags — these are behavioral, live in
config.yaml or CLI flags, NOT .env per AGENTS.md):
- `--min-liquidity` (default 5000 USDC), `--min-volume` (default 10000 USDC),
  `--categories` (default `crypto,politics`), `--limit` per request (default 100).
- **Category tagging: use Gamma `tag_id` API filtering** <!-- RED-TEAM F-10 --> (NOT client-side keyword regex). Discover with `GET {gamma}/markets?tag_id=<crypto|politics tag>&...`. Keyword derivation (`slug`/event tags) is a **fallback only** for markets where `tag_id` is absent. Store `category_confidence`: 1.0 when a single canonical tag matched; `<1.0` for multi-keyword/ambiguous matches → flag for **quarantine review** (excluded from scoring until reviewed). `category_override` (phase-00) lets `store.py recategorize <condition_id> <category>` fix miscategorization without a migration. (Validate category distribution later.)

## Interfaces

**Consumes** (from Phase 00):
- `store.upsert_market(...)` (with `category_confidence`), `store.create_scan(...)`/`store.finish_scan(...)`, `store.mark_outcome(...)`,
  `store.get_pending_resolution(...)`, `store.init_db()`, `store.get_db_path()`.  <!-- RED-TEAM F-03, F-04, F-06, F-10 -->
- Sibling skill knowledge: `GAMMA="https://gamma-api.polymarket.com"`,
  `CLOB="https://clob.polymarket.com"`, `DATA="https://data-api.polymarket.com"`. <!-- RED-TEAM F-02 --> **Verify V2 base URL LIVE before coding**; sibling pins V1.

**Produces** (exact signatures — predictor/crowd phases verify against):
- `markets_client.discover(categories:list[str], min_liquidity:float, min_volume:float, limit:int=100) -> list[dict]`
  each dict: `{condition_id, slug, question, category, category_confidence:float, clob_token_ids:list[str], outcome_prices:list[float], volume_usd:float, end_date}`  <!-- RED-TEAM F-10 -->
- `markets_client.run_scan(categories, min_liquidity, min_volume, limit) -> dict`  returns `{n_markets, by_category, ts, scan_id}`  <!-- RED-TEAM F-03 --> uses `create_scan` at start, `finish_scan` at end
- `prices_client.get_price(clob_token_id:str) -> dict`  `{yes_price:float, mid:float, spread:float}`  <!-- RED-TEAM F-02 --> asserts `0<yes_price<1` & mid∈[bid,ask]
- `prices_client.get_history(condition_id:str, interval="all", fidelity=50) -> list[dict]`  `[{t, p}, ...]`  <!-- RED-TEAM F-02 --> V2 endpoint shape TBD by probe
- `resolution_client.fetch_resolved(since_ts:str=None, limit:int=100) -> list[dict]`
  each: `{condition_id, outcome_int, resolved_ts, resolution_source, outcome_confidence, outcome_raw, resolution_status}`  <!-- RED-TEAM F-06 -->
- `resolution_client.run_resolution_check() -> dict`  `{n_resolved, n_quarantined, errors}`  <!-- RED-TEAM F-06 --> only resolves markets `closed` ≥7 days (or UMA finalized); quarantines void/disputed/ambiguous/non-binary

## Related Code Files

**Create** (under `skills/research/polymarket-signals/scripts/`):
- `markets_client.py`
- `prices_client.py`
- `resolution_client.py`
- `_http.py` (shared `_get(url, timeout=15)` + `_parse_json_field` + `_fmt_pct` — extracted DRY helper)

**Modify**:
- `references/api-endpoints.md` — fill in the Gamma/CLOB/Data endpoints actually used, with curl examples.
- `SKILL.md` — add `## How to Run` scan command + cron example.

**Delete**: none. **Core edits**: NONE.

## Implementation Steps

1. Write `scripts/_http.py`: copy the `_get`/`_parse_json_field`/`_fmt_pct`/`_fmt_volume`
   helpers from the sibling skill (single source of truth now; sibling keeps its own copy
   unchanged). Add `BASE = {"gamma": ..., "clob": ..., "data": ...}` constants.
2. `markets_client.py`: implement `discover()` — query `GET {gamma}/markets?active=true&closed=false&order=volume&ascending=false&limit=N`,
   filter client-side by liquidity/volume/category-derivation, parse double-encoded
   fields, return normalized dicts. Add `run_scan()` that loops `discover()` and calls
   `store.upsert_market()` + `store.log_scan()`. argparse CLI: `discover`, `scan`.
3. `prices_client.py`: `get_price()` hits `GET {clob}/midpoint?token_id=...` +
   `/spread?token_id=...`; `get_history()` hits `/prices-history?market={condition_id}&interval=&fidelity=`.
   Pure functions — no DB writes. CLI driver for debugging a single token.
4. `resolution_client.py`: `fetch_resolved()` queries `GET {gamma}/markets?closed=true&limit=N`
   (optionally `&end_date_min={since}`), reads resolved outcome from Gamma fields
   (`outcomePrices` final / `closed` + resolution source). `run_resolution_check()` calls
   `store.get_pending_resolution()`, matches against fetched, calls `store.mark_outcome()`.
   argparse CLI: `check`, `show-pending`.
5. Update `references/api-endpoints.md`: Gamma markets/events, CLOB midpoint/spread/
   prices-history, Data trades. One curl each. Note rate limits (Gamma 4k/10s, CLOB 9k/10s).
6. Update `SKILL.md` `## How to Run` with the cron scan command and a sample
   `hermes cron add` invocation (schedule string e.g. `every 12h`).
7. Smoke test against live APIs (read-only, globally OK): run `markets_client.py scan`,
   confirm rows in DB; run `resolution_client.py check` on an already-closed market.

## Todo List

- [ ] `_http.py` shared helpers (no duplication of `_get`)
- [ ] `markets_client.discover` returns normalized dicts, category-tagged
- [ ] `markets_client.run_scan` persists to store + logs scan
- [ ] `prices_client` get_price/get_history (no DB writes)
- [ ] `resolution_client.run_resolution_check` fills outcomes for pending markets
- [ ] `references/api-endpoints.md` filled with used endpoints
- [ ] Live smoke test: scan persists ≥1 crypto + ≥1 politics market
- [ ] No file >200 lines

## Success Criteria

- `run_scan()` with default filters persists only Crypto+Politics markets meeting
  min liquidity/volume; verify with `store.get_predictions`-style read on `markets`.
- `run_resolution_check()` flips at least one `outcomes` row when pointed at a
  recently-resolved market.
- All HTTP failures degrade gracefully (stderr + exit 1, never a stack trace in cron).
- Cost bound: a default scan fetches ≤100 markets (filter enforced). <!-- RED-TEAM F-11 --> **Note:** phase-02 caps `--max-markets` at ~20 (NOT 100) — the discover `limit` here bounds the *candidate* universe, but the predictor's per-scan LLM/web cost is bounded separately downstream.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Category mis-tagging corrupts calibration buckets | Med | High | Deterministic keyword rules + a manual category override stored on the markets row (phase 02 can correct). |
| Double-encoded JSON mishandled → crashes | Low | Med | Reuse sibling's battle-tested `_parse_json_field`; test on real Gamma payload. |
| Rate limits / network flakiness in cron | Low | Low | 15s timeout, stderr+exit1; cron retries next tick. No retry-storm. |
| Filter too loose → huge market universe, LLM cost blowup | Med | High | Hard `limit` default 100 on *discover* (candidate universe); **phase-02 `--max-markets` ~20 caps the LLM/web spend** (Red Team F-11). min liquidity/volume defaults; documented in SKILL.md. |

## Security Considerations

- All endpoints public/read-only — no auth, no keys in this phase.
- No user input is interpolated into URLs unencoded (`urllib.parse.quote` on slugs/queries).
- Resolution data is public; storing outcomes leaks nothing.

## Next Steps

- Unblocks **Phase 02** (predictor calls `markets_client.discover` + `prices_client.get_price`,
  logs predictions via `store.insert_prediction`).
- Resolution feed here is what Phase 04/05 score against — keep `run_resolution_check`
  runnable as its own cron.
