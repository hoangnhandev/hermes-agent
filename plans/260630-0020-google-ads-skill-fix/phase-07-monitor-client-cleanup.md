# Phase 07 — Standardize Monitor Client + customer_id

## Context Links
- Plan: [`plan.md`](plan.md)
- Findings: M1 (`load_from_storage` vs `load_from_env`), M2 (`login_customer_id` used as customer_id — wrong for MCC), M3 (SKILL.md cron `monitor.py full` vs real `--mode full`), M5 (`utcnow()` deprecated), L3 (monthly_budget rewrite loses origin)

## Overview
- **Priority**: P2
- **Status**: pending
- **Effort**: 2h
- One auth path (env), correct customer_id for MCC accounts, deprecated datetime calls fixed, CLI docs corrected.

## Key Insights
- M1: `monitor.py:41` uses `GoogleAdsClient.load_from_storage()` (reads YAML file `google-ads.yaml`); `deploy.py` uses `load_from_env()`. Two divergent auth paths → confusion. **Standardize on `load_from_env`** (matches env-file convention used everywhere else in skill).
- M2: `monitor.py` passes `self.googleads_client.login_customer_id` as `customer_id` to GAQL queries. For MCC (manager) accounts, `login_customer_id` = the manager, but queries must target the **child client customer_id**. Using login_customer_id queries the MCC shell → no campaign data. Fix: read `GOOGLE_ADS_CUSTOMER_ID` env (the child account) for queries; `login_customer_id` only used for auth header.
- M3: SKILL.md line 326 shows `monitor.py full` (positional) — real is `--mode full`. Doc bug.
- M5: `datetime.utcnow()` deprecated in 3.12+. Use `datetime.now(timezone.utc)`.
- L3: monitor overwrites `monthly_budget` from env on each sync, losing the per-campaign origin value recorded at creation. Preserve original; only fill if missing.

## Requirements
### Functional
- Monitor uses `load_from_env()` (single auth path).
- GAQL queries use `GOOGLE_ADS_CUSTOMER_ID` (child), not `login_customer_id`.
- All `datetime.utcnow()` → `datetime.now(timezone.utc)`.
- Preserve original `monthly_budget` per campaign.
### Non-functional
- `monitor.py` <200 lines (some logic moves to Phase 08 split helpers).

## Architecture
```
monitor.GoogleAdsSync.__init__:
  client = GoogleAdsClient.load_from_env()
  self.customer_id = os.getenv("GOOGLE_ADS_CUSTOMER_ID")
  # login_customer_id handled internally by client for MCC auth
query:
  customer_id=self.customer_id   # was: login_customer_id
```

## Interfaces
**Consumes:**
- env: `GOOGLE_ADS_CUSTOMER_ID`, `GOOGLE_ADS_LOGIN_CUSTOMER_ID` (auth only)
- `GoogleAdsClient.load_from_env()`

**Produces:**
- `monitor.GoogleAdsSync.customer_id` = child account (query target)

## Related Code Files
- **Modify**: `scripts/monitor.py` (load_from_env, customer_id, utcnow→now(timezone.utc), monthly_budget preserve)
- **Read-only**: SKILL.md (Phase 09 fixes the `monitor.py full` doc bug)

## Implementation Steps
1. `monitor.py:41`: `load_from_storage()` → `load_from_env()`. Verify env vars present (fail loud if not — consistent with Phase 05).
2. Add `self.customer_id = os.getenv("GOOGLE_ADS_CUSTOMER_ID")`. Replace all `self.googleads_client.login_customer_id` query args (lines 91,142,201) with `self.customer_id`.
3. Global replace `datetime.utcnow()` → `datetime.now(timezone.utc)`; add `timezone` to datetime import (Phase 01 adds `timedelta`; combine).
4. monthly_budget: only set from env if campaign row missing it; never overwrite existing.
5. Note SKILL.md line 326 doc bug for Phase 09.

## Todo List
- [ ] Switch monitor to load_from_env
- [ ] Use GOOGLE_ADS_CUSTOMER_ID for queries
- [ ] Fix utcnow → now(timezone.utc)
- [ ] Preserve original monthly_budget
- [ ] Test monitor --mode sync against test account (returns real data)

## Success Criteria
- `monitor.py --mode sync` returns real campaign metrics from test account (not empty MCC shell).
- `grep utcnow scripts/*.py` returns nothing.
- Single auth path (env) across deploy + monitor.

## Risk Assessment
- **Medium** — wrong customer_id has been silently returning no data; "fix" may surface other latent issues. **Mitigation**: verify against test account; compare GAQL output to Ads UI.
- **Low** — env var rename if current env uses different names. **Mitigation**: align to `google-ads.env.example`.

## Security Considerations
- Same env credentials; no new surface.

## Next Steps
- Depends on Phase 01. Phase 08 may further split monitor.py.
