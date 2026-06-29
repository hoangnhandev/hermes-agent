> ⚠️ **STATUS: DEFERRED (out of MVP, Red Team F-08).** Kept as reference for a future gated plan. Do not implement until phase-02 produces directional calibration signal.

# Phase 03 — Crowd Aggregates (Manifold + Metaculus ensemble)

## Context Links

- Design: `plans/20260626-polymarket-signal-bot-brainstorm.md` (§3 signal layer "Crowd", §5 phasing row 2).
- Overview: `plans/20260626-polymarket-signal-bot/plan.md`.
- Depends on: `phase-00` (`store.set_ensemble_breakdown`), `phase-02` (`predict.run_scan` insertion point).

## Overview

- **Priority**: P2 · **Status**: deferred · **Effort**: 5h
- `crowd_client.py`: query Manifold Markets + Metaculus for forecast aggregates on the
  same question, map to a 0..1 P, ensemble with the LLM P. Goal: a better-calibrated
  `predicted_p` and a richer `ensemble_breakdown` per prediction.

## Key Insights

- Crowd aggregates (esp. Metaculus community median) are empirically **well-calibrated** —
  they often beat naive LLM P. Ensemble (mean/trimmed-mean of LLM + crowd) is cheap
  insurance and directly improves the calibration curve Phase 04/05 measures.
- Question matching is the hard part: Polymarket questions ≠ Manifold questions ≠ Metaculus
  questions. Do fuzzy keyword/slug matching, fall back to "no match → skip source" (no hallucinated P).
- These APIs are free but rate-limited and occasionally shapeless — treat them as
  best-effort. A missing crowd source must never break the scan.

## Requirements

**Functional**
- `crowd_client.py`: `search_manifold(query)`, `search_metaculus(query)` → return
  normalized `{source, p, n_forecasters?, resolved_url, match_confidence}` or None.
- `ensemble(probs: list[float], weights: list[float]|None) -> float` (default: simple mean;
  trimmed-mean option; ignore None inputs).
- Wire into `predict.run_scan`: after `predict_one` (LLM P), call crowd sources, compute
  ensemble P, store via `set_ensemble_breakdown` + overwrite `predicted_p` with the ensemble.
- `sources` list on the prediction now reflects which sources contributed (e.g. `["llm","web","manifold"]`).

**Non-functional**
- stdlib-only HTTP (urllib/json). API keys (if any) read from `${HERMES_HOME:-~/.hermes}/.env`.
- Per-source timeout ≤10s; one failure does not abort the market's prediction.
- `crowd_client.py` <200 lines.

## Architecture

```
predict.run_scan loop (phase 02), per market:
   ├─ predict_one(market, context)         → llm_p           (phase 02)
   ├─ crowd_client.gather(market["question"]) → {manifold_p?, metaculus_p?}
   ├─ probs  = [llm_p] + [p for p in crowd if p is not None]
   │  weights default equal; (optional weighted config flag, NOT env)
   ├─ ensemble_p = ensemble(probs, weights)
   ├─ store.set_ensemble_breakdown(pred_id, {"llm":llm_p,"manifold":...,"metaculus":...,"final":ensemble_p})
   └─ overwrite predicted_p = ensemble_p on the prediction row (update by pred_id)
```

API specifics (fill `references/api-endpoints.md`):
- Manifold: `GET https://api.manifold.markets/v0/search-markets?term=<q>&filter=open&sort=liquidity`
  → parse `probability` (0..1) on the closest match. Anon access OK.
- Metaculus: `GET https://www.metaculus.com/api/v2/questions/?search=<q>&status=open`
  → community `quartiles`/`prediction` → map to P (binary question: `prediction`; continuous: skip).
  Free, optional `METACULUS_API_KEY` raises rate limit.

Match scoring: tokenize question, Jaccard/keyword overlap ≥ threshold (default 0.4) else None.
`match_confidence` stored in breakdown for later analysis.

## Interfaces

**Consumes**:
- Phase 02 `predict.predict_one(...)` (LLM P), `predict.run_scan` insertion point.
- `store.set_ensemble_breakdown(pred_id, breakdown)`, plus an `update_predicted_p(pred_id, new_p)`
  helper to add to `store.py` (see Modify below).
- `.env`: `MANIFOLD_API_KEY` (optional), `METACULUS_API_KEY` (optional).

**Produces** (exact signatures):
- `crowd_client.search_manifold(query:str, limit:int=5) -> dict|None`
  `{source:"manifold", p:float, url:str, match_confidence:float}`
- `crowd_client.search_metaculus(query:str, limit:int=5) -> dict|None`
  `{source:"metaculus", p:float, url:str, match_confidence:float}`
- `crowd_client.gather(question:str) -> dict`  `{"manifold":<dict|None>, "metaculus":<dict|None>}`
- `crowd_client.ensemble(probs:list[float|None], weights:list[float]|None=None, method="mean") -> float`
- `crowd_client.run_for_market(market:dict, llm_p:float) -> dict`
  `{final_p:float, breakdown:dict, sources:list[str]}`

## Related Code Files

**Create**:
- `scripts/crowd_client.py`

**Modify**:
- `scripts/store.py` — add `update_predicted_p(pred_id:int, new_p:float) -> None` (Phase 00
  schema anticipated `ensemble_breakdown`; this small helper is the only store change).
- `scripts/predict.py` — in `run_scan`, after `predict_one`, call
  `crowd_client.run_for_market(...)` and `store.set_ensemble_breakdown` +
  `store.update_predicted_p`. Guard with try/except so a crowd failure doesn't kill the scan.
- `references/api-endpoints.md` — Manifold + Metaculus endpoints + curl examples + rate notes.
- `SKILL.md` — `## Procedure` updated: crowd ensemble is now step 2.5; `## Prerequisites` lists optional keys.

**Delete**: none. **Core edits**: NONE.

## Implementation Steps

1. `crowd_client.py`: implement `_get(url, headers={}, timeout=10)` (reuse `_http._get`
   from Phase 01 if its signature allows custom headers; else local helper). Add the two
   search functions with normalization + match-confidence scoring.
2. Implement `ensemble()`: filter None, support `"mean"` and `"trimmed_mean"` (drop min/max
   if len≥3). Default equal weights. Keep it pure (no I/O) — unit-testable.
3. Implement `run_for_market(market, llm_p)`: gather → build probs list → ensemble →
   return breakdown dict. `sources` derived from which crowd results were non-None.
4. Extend `store.py` with `update_predicted_p` (one-liner UPDATE; parameterized).
5. Patch `predict.run_scan`: insert crowd ensemble between predict_one and insert/edge-eval.
   The `predicted_p` stored becomes the ensemble; `market_p` unchanged; `sources` updated.
6. Update `references/api-endpoints.md` and `SKILL.md` (Procedure + Prerequisites + a
   `## Pitfalls` note: "crowd sources best-effort; missing source ≠ scan failure").
7. Smoke test: pick one crypto + one politics market with obvious Manifold equivalents,
   confirm breakdown is populated and `final_p` is a valid blend.

## Todo List

- [ ] `search_manifold` / `search_metaculus` return normalized dicts or None
- [ ] Match-confidence threshold filters bad matches (no hallucinated crowd P)
- [ ] `ensemble` handles None + single-element + multi-element cases
- [ ] `store.update_predicted_p` added + parameterized
- [ ] `predict.run_scan` ensemble step is fault-tolerant (crowd failure → LLM-only fallback, logged)
- [ ] Breakdown persisted on every prediction that reached ensemble
- [ ] references + SKILL.md updated
- [ ] No file >200 lines

## Success Criteria

- For markets with a crowd match, `ensemble_breakdown` is non-empty and `predicted_p`
  reflects the ensemble; for markets without, scan continues with LLM P only (logged).
- Calibration curve (once Phase 04 computes it) should tighten vs Phase 02 LLM-only —
  noted as the success signal, measurable only after enough resolves.
- No scan aborts due to a crowd API outage (verify by simulating a timeout).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Bad question match → wrong crowd P injected | Med | High | Match-confidence threshold; store `match_confidence`; allow Phase 04 gating to down-weight low-confidence matches. |
| Crowd API outage breaks scan | Med | Med | Per-source try/except + 10s timeout; LLM-only fallback path. |
| Ensemble weights tuned too aggressively early (overfit) | Low | Med | Default equal weights; weights are a config.yaml/flag concern, not hardcoded magic. |
| Metaculus continuous questions misread as binary P | Med | Med | Type-check question kind; skip non-binary. Documented in pitfalls. |

## Security Considerations

- Optional API keys read from `.env`; never logged. Anon access is the default.
- Crowd-sourced URLs/titles are untrusted → stored as data, never rendered as executable.
- No auth flows; all reads.

## Next Steps

- Unblocks **Phase 04** (specialized data + calibrated gating; gating now operates on
  the richer ensemble `predicted_p` and the `sources` dimension).
- The `match_confidence` stored here becomes a feature Phase 04/05 can slice calibration by.
