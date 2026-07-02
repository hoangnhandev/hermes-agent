# Code Review — google-ads flow loop-closure (plan 260702-0927)

## Scope
- Files: 16 (skill `scripts/*` 11 + infra `schema.sql/sync.js/index.js/anomalies.js` 4 + dashboard 3 + env/SKILL)
- LOC: +576/−66 (uncommitted working tree vs HEAD `b62b8794f`)
- Focus: money-safety, GAQL/API v21 correctness, dedupe/idempotency, error propagation
- Phases: A (monitor pipeline), B (optimize loop + anomaly→Telegram + D1/dashboard), C (deploy negatives, env, account-local dates)

## Overall
Clean, well-commented implementation. **Money axis is SAFE** — no path新增 spend:
negatives only BLOCK; optimize recommend-only; deploy rollback intact after negatives
insertion; MONTHLY_BUDGET warn is non-blocking. Findings below are noise/robustness,
not spend. Verdict: **APPROVE_WITH_NITS**.

## Money-safety (verify area 1) — PASS
- `create_negative_keywords`: campaign-level `CampaignCriterion`, `negative=True`,
  catches `GoogleAdsException` + bare `Exception`, returns `[]`. Cannot raise into
  deploy. Negatives only reduce reach → cannot increase spend. ✓
- Rollback paths (ad_group/keyword/ad fail) only `_pause_campaign`; orphan negatives
  on a paused campaign are inert. Negatives inserted between keywords+ads is safe. ✓
- `optimize`: status=`'recommended'`, no `--apply`/auto-mutate. Columns are display
  only. `_log_actions` is INSERT-only logging. ✓
- `creator.run_budget_guardrails`: <1M warn prints, does NOT block. Existing
  hard-cap refusal logic untouched. ✓
- `has_conversion_tracking` rejects placeholder `1234567890` → CPA rule can't fire
  on un-wired tracking. ✓

## Correctness (verify areas 2, 3) — PASS
- **GAQL `keyword_view`** (monitor.query_keyword_metrics): field names valid for
  google-ads v21 — `segments.date`, `campaign.id/status`, `ad_group.id`,
  `ad_group_criterion.keyword.text/match_type`, `ad_group_criterion.status`, all
  standard metrics. `match_type.name.lower()` correctly maps the enum. `keyword_view`
  reflects positive (biddable) keywords only, so negatives won't pollute. ✓
- **CampaignCriterion negative kw** (deploy): `op.create`→`cc.campaign`,
  `cc.negative=True`, `cc.keyword.text`, `cc.keyword.match_type=…PHRASE`,
  `service.mutate_campaign_criteria(customer_id, operations)`. Correct v21 path. ✓
- **Auth `/api/anomalies`**: falls through global `verifyAuth` gate (index.js:56),
  NOT in the bypass list. No auth bypass. Comment accurate. ✓
- **XSS**: `renderAnomalies` runs every interpolation through `esc()`; numeric
  cells use `formatNumber`/`toFixed`. Safe. ✓
- **sync_to_d1.py indentation** (your Serena-bug concern): `__init__`,
  `get_unsynced_anomalies`, `build_sync_payload` all cleanly indented at 8-space
  class-body level; signature/arg alignment correct. ✓
- **synced_to_d1/alert_sent decoupling**: `get_unsynced_anomalies` keys on
  `COALESCE(synced_to_d1,0)=0`; `mark_synced` sets `synced_to_d1=1`; Telegram path
  sets `alert_sent=1` independently. Four states all reachable, none lost/duped
  via the decoupling itself. ✓
- **Backfills idempotent**: `synced_to_d1` (PRAGMA-guarded in `_store` + `D1Sync`),
  `optimization_log` magnitude/expected/status via `_ensure_column`. Re-runs no-op. ✓
- **optimize INSERT accounting**: 10 cols, 9 `?` + `'recommended'` literal, 9 params. ✓

## Issues

### M1 — anomaly dedupe ↔ save accumulates dups during Telegram outage (propagates to D1)
`_already_alerted` gates on `alert_sent=1`. If Telegram send fails, the row stays
`alert_sent=0`, so the next sync passes the dedupe check and `save_anomaly` INSERTs
a NEW row (no UNIQUE on anomaly_log). Cycle repeats every sync → anomaly_log bloat
(~2–4 rows/hr/anomaly at cron cadence). D1 sync then ships all copies; D1 PK is
`(detected_at, entity_id, anomaly_type)` but `detected_at=datetime('now')` is a full
timestamp → distinct per row → `INSERT OR IGNORE` does NOT dedupe → dashboard shows
stacked duplicate alerts.
- Impact: signal/cardinality noise only; no spend.
- Root cause: "save once/day" and "retry send until success" are conflated through
  one flag.
- Fix (pick): either (a) add existence dedupe in `save_anomaly` on
  `(entity_id, anomaly_type, date(detected_at))` so only ONE row/day is written and
  the send-retry loop targets that single unalerted row; or (b) make the D1 PK use
  `DATE(detected_at)` not the full timestamp so D1 at least dedupes downstream.

### M2 — sync.js anomalies loop not per-row isolated (one bad row blocks all syncs)
`handleSync` processes anomalies in a `for` loop with no per-iteration try/catch;
each `env.DB.prepare(...).run()` can throw (transient D1 error, NOT NULL violation
on `metric_name`, schema drift). A throw propagates to the outer try → whole POST
returns failure → `mark_synced` never runs → metrics/campaigns/keywords/anomalies
retry en bloc every cycle until that one row clears. Anomalies run BEFORE the
metrics batch in the flow, so a bad anomaly blocks the biggest batch too.
- Impact: sync robustness; no deploy path affected.
- Fix: wrap each anomaly insert in `try { … } catch(e) { console.warn; continue }`
  (mirroring the resilience pattern expected elsewhere); consider same for any
  non-batched per-row loop.

### L1 — dedupe "today" is UTC, detection "today" is account-local (wire 6c inconsistency)
`_already_alerted` uses SQLite `date('now')` (UTC); `detect_anomalies` selects the
day via `account_local_today()` (UTC+7). At the VN day edge the dedupe window can
re-ping or skip once. `_dates.py` explicitly reserves account-local for "day of
comparison" — the dedupe window qualifies and should match.
- Fix: bind `account_local_today()` as a param in `_already_alerted` instead of
  `date('now')`.

### Nits
- `syncedCounts.anomalies++` counts attempts, not successful inserts (`INSERT OR
  IGNORE` may skip) → sync summary over-reports. Cosmetic.
- DRY: `anomaly_log.synced_to_d1` backfill duplicated in `_store.create_tables`
  AND `D1Sync.__init__`. Canonical home is `_store`; `D1Sync`'s copy is defensive
  but redundant.
- deploy.py comment "Done BEFORE ads so a bad negative never blocks" is misleading
  — non-fatal try/catch is what prevents blocking, ordering is irrelevant. Doc only.
- `optimization_log` has no UNIQUE → re-running `analyze` for the same period
  re-INSERTs recommendations (pre-existing; new cols don't change it). Not a
  regression introduced here.

## Positive
- Money-safety reasoning in comments is accurate and matches code.
- Telegram path is correctly best-effort at TWO layers (lazy import try/except +
  per-send try/except) — sync never blocked.
- `has_conversion_tracking` placeholder rejection is a thoughtful guard.
- D1 `INSERT OR IGNORE` + PK is the right idempotency primitive (modulo M1/M2).
- Escaping discipline in `renderAnomalies`.
- `_ensure_column` is a clean idempotent primitive.

## Metrics
- Type/lint: not run (no type step for py here; JS untyped). Syntax: all files
  importable-shaped; indentation spot-checked per your ask.
- Tests: none in diff (skill has no test suite; live API untestable w/o Dev Token).
- Money-safety regressions: 0.

## Unresolved
1. Real `google-ads.env` MONTHLY_BUDGET (gitignored) — can't verify the claimed
   500→5,000,000. Example shows 6,000,000; warn threshold is 1,000,000. Verify on
   the live VPS.
2. GAQL/API v21 field correctness judged from google-ads-python knowledge only;
   no live API test possible (no Developer Token).
3. M1 design intent: is within-day re-save during outage acceptable, or should
   save dedupe to 1/day with send-only retry? Needs product call.
