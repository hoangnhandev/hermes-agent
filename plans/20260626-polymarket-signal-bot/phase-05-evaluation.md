> ⚠️ **STATUS: DEFERRED (out of MVP, Red Team F-08).** Kept as reference for a future gated plan. Do not implement until phase-02 produces directional calibration signal.

# Phase 05 — Evaluation Report + Go/No-Go

## Context Links

- Design: `plans/20260626-polymarket-signal-bot-brainstorm.md` (§5 phasing row 4, §6 calibration model, §8 success metrics, §9 out of scope).
- Overview: `plans/20260626-polymarket-signal-bot/plan.md`.
- Depends on: `phase-04` (`score`, `calibration_state`, `resolve_check`).

## Overview

- **Priority**: P2 · **Status**: deferred · **Effort**: 4h
- `report.py`: generate a calibration + paper-trade evaluation (Brier per category,
  calibration curve, paper-trade PnL, alert precision). Deliver via CLI + optional
  periodic Telegram summary. Conclude with a documented **go/no-go** for any future
  automation — which remains explicitly out of scope to implement.

## Key Insights

- This phase is the payoff for the calibration spine: an honest, evidence-based verdict
  on whether the signal system has real edge. Brainstorm §2 is blunt — naive LLM ≈ no edge;
  the report must be willing to say "no edge, keep paper-trading".
- The decision is the deliverable. Phase 05 does NOT build automation even if the verdict
  is "go" — that's locked out of scope. It only produces the recommendation + evidence.
- Alert precision (brainstorm §8) closes the loop: of alerts that fired, how many moved
  in the predicted direction. This is the user-facing quality metric.

## Requirements

**Functional**
- `report.py generate`: pull resolved predictions + calibration_state, produce:
  - Per-category Brier score + comparison to 0.5 baseline.
  - Calibration curve table (deciles) per category.
  - Paper-trade PnL (total + per category), with the fee/spread proxy made explicit.
  - Alert precision: of gated alerts that have since resolved, fraction correct-direction.
  - Headline go/no-go recommendation with the threshold rules stated.
- `report.py render`: text + optional markdown for Telegram; ASCII calibration curve for terminal.
- Optional periodic Telegram delivery via a Hermes cron job (schedule configurable).

**Non-functional**
- Report reads only from the store + `calibration_state`; no live network needed (deterministic, replayable).
- Pure rendering — no side effects. <200 lines.

## Architecture

```
report.py generate [--category C] [--since YYYY-MM-DD]
   ├─ store.get_predictions(resolved_only=True)
   ├─ score.brier / score.calibration_curve / score.realized_edge
   ├─ compute alert_precision over predictions that fired an alert (need an `alerted` flag — see Modify)
   └─ assemble report dict

report.py render --format text|markdown
   → stdout (cron delivers stdout to Telegram)

cron (optional, e.g. weekly):
   hermes cron add "every monday 9am" --skill polymarket-signals \
       --script "python3 scripts/report.py generate --format markdown"
```

Go/no-go rule (made explicit; conservative):
```
GO (per category) iff ALL:
  n_resolved >= MIN_N_REPORT          (e.g. 50, stricter than phase 04 gating)
  brier(category) < brier_baseline(0.5) by a margin (e.g. brier < 0.22)
  mean_calibration_gap < CAL_TOL
  realized_edge(category) > 0 post fee/spread proxy
  alert_precision(category) >= 0.55
Otherwise: NO-GO — continue paper-trading; do not automate.
```
All thresholds behavioral → CLI flags / config.yaml, not .env.

## Interfaces

**Consumes**:
- `store.get_predictions(category, resolved_only=True)`, `store.get_calibration_state(category)`,
  and a new `store.get_alerted_predictions(category)` (see Modify — needs an `alerted` marker).
- `score.brier`, `score.calibration_curve`, `score.realized_edge`, `score.category_calibration`.

**Produces** (exact signatures):
- `report.generate(category:str|None=None, since:str|None=None) -> dict`
  `{as_of_ts, categories:[{category, n_resolved, brier, baseline_brier, calibration_gap, realized_edge, alert_precision, go_no_go, curve:[...]}], headline_go_no_go:str}`
- `report.render(report:dict, fmt:str="text") -> str`
- `report.decide_go_no_go(category_state:dict) -> dict`  `{decision:"GO"|"NO-GO", reasons:list[str]}`

## Related Code Files

**Create**:
- `scripts/report.py`

**Modify**:
- `scripts/store.py` — add `alerted INTEGER DEFAULT 0` column to `predictions` (schema
  migration: `ALTER TABLE ... ADD COLUMN` is safe/idempotent-guarded) +
  `mark_alerted(pred_id)` + `get_alerted_predictions(category=None)`. Phase 02/04 `run_scan`
  sets `alerted=1` whenever an alert actually fired (one-line change in `predict.run_scan`).
- `scripts/predict.py` — call `store.mark_alerted(pred_id)` at the moment an alert is emitted.
- `scripts/score.py` — add `brier_baseline()` constant helper (0.25, the always-0.5 Brier)
  if not already present (keeps the baseline in one place, DRY).
- `references/calibration.md` — add the go/no-go rule + the MIN_N_REPORT stricture.
- `SKILL.md` — `## How to Run` adds the weekly report cron; `## Verification` section
  shows how to read a report and what GO vs NO-GO means.
- `plan.md` (overview) — mark all phases complete once this phase ships.

**Delete**: none. **Core edits**: NONE.

## Implementation Steps

1. Extend `store.py`: add `alerted` column with an idempotent migration (check
   `PRAGMA table_info` before ALTER), `mark_alerted`, `get_alerted_predictions`.
2. Patch `predict.run_scan` (Phase 02/04) to call `mark_alerted` on alert emission.
3. `report.py`: `generate()` aggregates per category, computes metrics via `score`,
   computes alert_precision = mean(predicted direction == outcome direction) over alerted+resolved.
4. `decide_go_no_go()`: apply the rule above; return decision + reasons list.
5. `render()`: text + markdown formatters. Include an ASCII calibration curve
   (decile buckets, `#` proportional to `emp_freq`). Headline line: `GO`/`NO-GO` per category.
6. Update `references/calibration.md` with the go/no-go rule and the stricter `MIN_N_REPORT`.
7. Update `SKILL.md` How to Run + Verification.
8. Smoke test: run `report.py generate` on accumulated history; even with little data it
   must produce a valid NO-GO (insufficient history) without error.

## Todo List

- [ ] `alerted` column migration idempotent; `mark_alerted` / `get_alerted_predictions` added
- [ ] `predict.run_scan` marks alerted predictions
- [ ] `report.generate` returns the full metrics dict per category
- [ ] `decide_go_no_go` applies the conservative rule, returns reasons
- [ ] `render` produces readable text + markdown + ASCII curve
- [ ] `references/calibration.md` documents the go/no-go rule
- [ ] SKILL.md How to Run + Verification updated
- [ ] Smoke test: NO-GO-on-insufficient-history path works cleanly
- [ ] No file >200 lines

## Success Criteria

- Report reproduces brainstorm §8 success metrics: n predictions, % resolved, Brier per
  category, calibration curve, paper-trade PnL, alert precision.
- A go/no-go decision is emitted per category with explicit reasons; NO-GO is the expected
  outcome until strong evidence accumulates (and the system says so honestly).
- Report is deterministic from the store (re-running on the same DB yields identical output).
- All downstream automation is explicitly out of scope — the report STOPS at the recommendation.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Report overstates edge → user automates prematurely | Med | High | Conservative multi-criteria GO rule; every GO must clear ALL thresholds; fee/spread proxy subtracted; report states "automation is out of scope". |
| `alerted` migration breaks existing DBs | Low | High | Idempotent ALTER guarded by PRAGMA check; tested on a DB created in Phase 00. |
| Metrics disagree with `score` outputs | Low | Med | `report` consumes `score` functions directly (DRY) — single source of math. |
| Report cron spams Telegram | Low | Low | Weekly default; markdown summary, not raw tables. |

## Security Considerations

- No secrets in reports. Rationale text (LLM-generated) is included but truncated.
- Reports are derived from public market data — safe to deliver over Telegram.

## Next Steps

- This is the terminal phase. Outcome options after the first evaluation window:
  1. **NO-GO** (most likely initially): keep the cron running, accumulate history, re-evaluate monthly.
  2. **GO on a category**: a *separate, future* plan would decide any automation — explicitly out of scope here per brainstorm §9.
- Open questions from the brainstorm (#1 polling source, #4 periodic dashboard) get a final
  answer in the report's "coverage notes" and the optional weekly Telegram delivery.

## Unresolved Questions (carry into implementation)

- Confirm Hermes cron `--script`/`--skill` flag shape against current `cron/jobs.py` docs before finalizing SKILL.md How-to-Run examples (Phase 02/04/05).
- Confirm the exact gateway mechanism for per-scan alerts (cron session stdout delivery vs. an explicit `/send`/gateway API call) — Phase 02 wires this.
- Pick free politics-polling source (or confirm crowd aggregates suffice) — Phase 04 open note.
