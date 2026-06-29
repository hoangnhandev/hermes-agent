# Phase 05 — Harden Deploy Client + Partial-Failure Rollback

## Context Links
- Plan: [`plan.md`](plan.md)
- Findings: H1 (silent mock on missing creds), H2 (no rollback on partial deploy)

## Overview
- **Priority**: P2 (robustness — prevents orphan spend)
- **Status**: pending
- **Effort**: 2h
- Make `get_client` fail hard (no silent mock) and add cleanup when ad-group/keywords/ads fail after campaign creation.

## Key Insights
- H1: `deploy.get_client` returns `MockGoogleAdsClient` when env file missing OR load throws → silent mock. A real `creator.py` run could "succeed" against mock and report victory while nothing deployed.
- H2: `deploy_full_campaign` creates campaign, then ad group, keywords, ads. If ad-group fails, campaign stays alive (ENABLED, spending) with no ads → wasted budget. Need rollback: on mid-stage failure, REMOVE the campaign + budget.

## Requirements
### Functional
- Missing `google-ads.env` or failed `load_from_env` → raise, unless `--mock` flag passed explicitly.
- If `create_ad_group`/`create_keywords`/`create_ads` fail after campaign created → remove campaign + its budget (or set PAUSED + alert).
### Non-functional
- Rollback itself retried; if rollback fails → loud alert (Telegram), leave campaign PAUSED not ENABLED.

## Architecture
```
deploy_full_campaign:
  create budget → create campaign
  try: create ad_group → keywords → ads
  except stage failure:
    rollback: remove campaign (REMOVED), remove budget
    if rollback fails: set campaign PAUSED + alert
  return success only if all stages ok
```

## Interfaces
**Consumes:**
- `GoogleAdsClient.load_from_env()`
- env credentials

**Produces:**
- `deploy.get_client(env_file, allow_mock=False) -> GoogleAdsClient` (raises if !allow_mock and no creds)
- `deploy._rollback_campaign(client, customer_id, campaign_resource_name, budget_resource_name) -> bool`
- `deploy.deploy_full_campaign(...) -> dict` (adds `rolled_back: bool` field on failure)

## Related Code Files
- **Modify**: `scripts/deploy.py` (get_client, deploy_full_campaign, new _rollback_campaign)
- **Read-only**: creator.py (passes allow_mock from --mock flag)

## Implementation Steps
1. `get_client`: add `allow_mock=False` param. If `not allow_mock and (not env_file or load fails)` → `raise RuntimeError("Google Ads credentials missing; pass --mock to force mock")`. Keep MockGoogleAdsClient only behind `allow_mock=True`.
2. `_rollback_campaign`: use CampaignService mutate (REMOVE) + CampaignBudgetService mutate (REMOVE). Retry on transient.
3. `deploy_full_campaign`: wrap ad-group/keywords/ads in try/except; on failure call `_rollback_campaign`; if rollback fails → mutate campaign status PAUSED + return `{success:False, rolled_back:False, alert:True}`.
4. `creator.main`: add `--mock` flag → `deploy.get_client(allow_mock=args.mock)`.

## Todo List
- [ ] get_client fail-hard with allow_mock param
- [ ] Implement _rollback_campaign
- [ ] Wire rollback into deploy_full_campaign
- [ ] Add --mock flag to creator.py
- [ ] Test rollback on test account (force ad-group failure)

## Success Criteria
- `creator.py` with no env file → exits non-zero with clear error (no mock).
- `creator.py --mock` → runs against mock (explicit).
- Forced ad-group failure on test account → campaign + budget removed within seconds.

## Risk Assessment
- **Medium** — rollback REMOVE may fail if campaign already serving. **Mitigation**: PAUSED fallback + Telegram alert; human can intervene.
- **Low** — test-account cleanup clutter. **Mitigation**: use test account's own budget.

## Security Considerations
- Rollback uses same authenticated client; no new cred surface.

## Next Steps
- Depends on Phase 02 (deploy wiring). Verified end-to-end in Phase 09.
