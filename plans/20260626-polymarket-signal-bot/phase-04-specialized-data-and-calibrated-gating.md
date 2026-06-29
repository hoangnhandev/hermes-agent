> ⚠️ **STATUS: DEFERRED (out of MVP, Red Team F-08).** Kept as reference for a future gated plan. Do not implement until phase-02 produces directional calibration signal.

# Phase 04 — Specialized Data + Calibrated Gating + Resolve Check

## Context Links

- Design: `plans/20260626-polymarket-signal-bot-brainstorm.md` (§3 data layer specialized, §6 calibration model, §5 phasing row 3, §7 data-fallback risk).
- Overview: `plans/20260626-polymarket-signal-bot/plan.md`.
- Depends on: `phase-01` (resolution_client), `phase-02` (predict alerts), `phase-03` (ensemble P).

## Overview

- **Priority**: P2 · **Status**: deferred · **Effort**: 6h
- Add specialized context sources (politics polling, crypto CoinGecko/on-chain) for the
  LLM, AND turn on **calibrated gating**: alerts only fire when (a) the category has
  enough resolved history, (b) that category is historically calibrated, and (c) realized
  edge > 0. Also stand up the `resolve_check.py` cron that fills outcomes and recomputes
  calibration. This is where "uncalibrated" disclaimers can finally come off — conditionally.

## Key Insights

- **Calibration is the product.** Until this phase, every alert is a paper-trade disclaimer.
  The gating logic here is the honest evidence layer that earns (or denies) trust.
- Need **enough resolved history** before gating engages. Define a minimum (e.g. ≥30
  resolved per category) — below it, alerts stay "uncalibrated". This avoids premature trust.
- Specialized data is the most failure-prone (polling APIs are sparse/paid). Build it last,
  keep it optional, and fall back to crowd aggregates (brainstorm §7). Never block the scan on it.

## Requirements

**Functional**
- `data_client.py`: `get_politics_context(question)` (polling — Manifold/Metaculus may
  substitute; honest note if no good free source), `get_crypto_context(question)` (CoinGecko
  price/volume + optional on-chain note). Returns context strings fed to the LLM predictor.
- `score.py`: `brier(predictions, outcomes)`, `calibration_curve(predictions, outcomes, buckets=10)`,
  `category_calibration(category, min_n=30)`, `realized_edge(category)` (paper-trade PnL proxy),
  `gating_decision(category, edge)` → `{alert:bool, reason:str}`.
- `resolve_check.py`: cron entrypoint → `resolution_client.run_resolution_check()` →
  `score.recompute_category_calibration()` → write a small `calibration_state` cache (table or JSON).
- `predict.run_scan`: pull specialized context per category, AND consult `score.gating_decision`
  before alerting. Alert text now includes calibration stats when gating allowed it; otherwise
  retains the "uncalibrated — paper trade" disclaimer.

**Non-functional**
- All scoring is pure-Python (numpy-free; stdlib `statistics`). Unit-testable without network.
- Specialized data calls are best-effort, timeout ≤10s, never fatal.
- `score.py`, `data_client.py`, `resolve_check.py` each <200 lines.

## Architecture

```
resolve_check cron (e.g. daily)
   ├─ resolution_client.run_resolution_check()    # fill outcomes
   ├─ score.recompute_all()                       # Brier + curve per category
   └─ write calibration_state.json (or table)

predict.run_scan (phase 02 + 03 + this phase):
   per market:
     ├─ context += data_client.get_<category>_context(question)   # best-effort
     ├─ ... llm + crowd ensemble (phase 02/03) ...
     ├─ gate = score.gating_decision(category, edge=predicted_p - market_p)
     └─ alert only if gate.alert == True
            message includes calibration stats + "calibrated category" note
            OR retains "uncalibrated — paper trade" when gate.reason says so
```

Gating rule (brainstorm §6, made precise):
```
alert = (
    n_resolved(category) >= MIN_N                         # e.g. 30
    and calibration_gap(category) < CAL_TOL               # |mean(pred) - mean(outcome)| per bucket < tol, e.g. 0.08
    and realized_edge(category) > 0                       # paper-trade PnL positive post fee/spread proxy
    and abs(edge) > EDGE_THRESHOLD                        # phase 02 absolute edge
)
```
All thresholds behavioral → config.yaml / CLI flags, NOT .env.

Calibration state persisted: `calibration_state(category, n_resolved, brier,
mean_calibration_gap, realized_edge, computed_ts)` — add as a 5th table OR a
`~/.hermes/polymarket_signals_cal.json` sidecar (pick table for atomicity; see Steps).

## Interfaces

**Consumes**:
- `resolution_client.run_resolution_check()` (Phase 01).
- `store.get_predictions(category=, resolved_only=True)`, `store.mark_outcome` (Phase 00).
- `predict.run_scan` insertion points for context + gating (Phase 02/03).

**Produces** (exact signatures):
- `data_client.get_politics_context(question:str) -> str|None`
- `data_client.get_crypto_context(question:str) -> str|None`
- `score.brier(preds:list[float], outs:list[int]) -> float`
- `score.calibration_curve(preds:list[float], outs:list[int], buckets:int=10) -> list[dict]`
  each `{bucket_lo, bucket_hi, n, mean_pred, emp_freq}`
- `score.category_calibration(category:str, min_n:int=30) -> dict|None`
  `{category, n_resolved, brier, mean_calibration_gap, realized_edge, computed_ts}` or None if `n<min_n`
- `score.realized_edge(category:str) -> float`  (mean paper-trade PnL per resolved prediction, fee/spread proxy subtracted)
- `score.gating_decision(category:str, edge:float) -> dict`
  `{alert:bool, reason:str, calibration:dict|None}`
- `resolve_check.run() -> dict`  `{n_newly_resolved, categories_recomputed, ts}`

Paper-trade PnL definition (per resolved prediction): bet fixed fraction at `market_p`;
payout = `outcome_int` (1 → +`(1-market_p)`, 0 → `-market_p`), minus a fee/spread proxy
(default 0.02, configurable). `realized_edge` = mean across resolved predictions in category.

## Related Code Files

**Create**:
- `scripts/data_client.py`
- `scripts/score.py`
- `scripts/resolve_check.py`

**Modify**:
- `scripts/store.py` — add `calibration_state` table + `upsert_calibration_state(category, ...)`
  and `get_calibration_state(category)`. (Phase 00 schema anticipated scoring; this adds the cache table.)
- `scripts/predict.py` — `run_scan`: (1) merge specialized context, (2) call
  `score.gating_decision` before alerting, (3) branch alert text calibrated vs uncalibrated.
- `references/calibration.md` — fill in Brier formula, calibration-curve definition, gating
  rule (verbatim from above), paper-trade PnL definition. This becomes the canonical ref.
- `references/api-endpoints.md` — polling/CoinGecko endpoints used + honest coverage notes.
- `SKILL.md` — `## Procedure` gets the gating step; `## How to Run` adds the daily
  `resolve_check` cron; `## Pitfalls` adds "calibration needs weeks; do not trust early".

**Delete**: none. **Core edits**: NONE.

## Implementation Steps

1. `score.py` first — pure functions, no I/O. Implement `brier`, `calibration_curve`,
   `realized_edge`, `category_calibration`, `gating_decision` with the exact signatures.
   Use only `statistics` + stdlib. Defaults: `MIN_N=30`, `CAL_TOL=0.08`, fee/spread proxy 0.02.
2. Extend `store.py`: add `calibration_state` table + upsert/get. Idempotent.
3. `resolve_check.py`: orchestrate resolution_client → score over resolved predictions →
   upsert_calibration_state. argparse: `run`, `show [--category C]`. Designed as its own
   daily cron, decoupled from the prediction scan.
4. `data_client.py`:
   - `get_crypto_context`: CoinGecko free endpoint (`/simple/price` / `/coins/{id}`) via
     keyword→coin-id map (bitcoin, ethereum). Best-effort; optional `COINGECKO_API_KEY` demo key.
   - `get_politics_context`: try Manifold/Metaculus aggregated commentary first (reuse
     crowd_client matches); if no good free polling API, return None + log an honest note.
     Document the limitation in `references/api-endpoints.md` (brainstorm open Q #1).
5. Patch `predict.run_scan`: prepend specialized context to the LLM user message; after
   ensemble + edge, call `score.gating_decision(category, edge)`; branch `format_alert`.
   Update `format_alert` to render calibration stats when `gate.alert` is True.
6. Update `references/calibration.md` as the canonical reference (formulas + gating rule).
7. Update `SKILL.md` Procedure + How to Run + Pitfalls.
8. Smoke tests: unit-test `score` with synthetic data (perfectly calibrated vs skewed);
   run `resolve_check.run` on the (still small) accumulated history and confirm it writes
   calibration_state and gates OFF while `n_resolved < MIN_N`.

## Todo List

- [ ] `score.py` pure functions with the exact signatures
- [ ] `calibration_state` table + upsert/get in store.py
- [ ] `resolve_check.run` recomputes per-category state, idempotent
- [ ] `data_client` crypto path returns context; politics path returns None gracefully when no source
- [ ] `predict.run_scan` consults `gating_decision`; alerts gated off until evidence
- [ ] `format_alert` shows calibration stats when calibrated, disclaimer otherwise
- [ ] `references/calibration.md` is the canonical formulas+gating reference
- [ ] Unit tests for `score` (synthetic calibrated + skewed fixtures)
- [ ] No file >200 lines

## Success Criteria

- With `< MIN_N` resolved predictions in a category, **zero** calibrated alerts fire
  (all retain the uncalibrated disclaimer) — verify by inspection.
- After resolves accumulate and a category crosses `MIN_N` with a good calibration gap +
  positive realized edge, that category's alerts switch to calibrated wording.
- `resolve_check` cron is independently runnable and updates `calibration_state` atomically.
- Specialized-data outage does not break the scan (crypto fallback to crowd/LLM-only; politics None).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Trusting calibration before enough data | Med | High | Hard `MIN_N` floor (30); gating returns `alert=False, reason="insufficient_history"` below it. |
| Polling API absent/paid → politics context empty | High | Med | Documented; fall back to crowd; do not block. Honest note in ref + alert. |
| Calibration curve noisy with small N per bucket | High | Med | Require `MIN_N` total AND report per-bucket `n`; gate off if any bucket < k (e.g. 3). |
| Fee/spread proxy unrealistic → fake edge | Med | High | Proxy is conservative (default 0.02); configurable; clearly labeled "proxy" in reports. Phase 05 stress-tests it. |
| Resolve cron diverges from scan (stale outcomes) | Med | Med | `resolve_check` daily; `predict.run_scan` treats calibration_state as read-only cache; recompute is cheap. |

## Security Considerations

- Optional CoinGecko key in `.env`, anon default. Polling sources are public.
- No trading, no keys beyond free API keys.
- Calibration data is derived from public market resolutions — no PII, no secrets.

## Next Steps

- Unblocks **Phase 05** (evaluation report consumes `score` + `calibration_state`).
- Once a category passes gating for several scan cycles, Phase 05 decides go/no-go on any
  future automation (which remains out of scope here).
