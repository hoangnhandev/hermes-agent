# Phase 02 — Wire creator → Real Deploy

## Context Links
- Plan: [`plan.md`](plan.md)
- Findings: C2 (creator deploy is stub), H3 (retry catches wrong exception), budget-math (cap self-includes proposed), L1 (RSA get_type)
- Parent: [`../260629-1125-hermes-ads-copilot/phase-03-skill-creator.md`](../../260629-1125-hermes-ads-copilot/phase-03-skill-creator.md)

## Overview
- **Priority**: P1 (blocker — the core "create real campaign" capability)
- **Status**: pending
- **Effort**: 4h
- Replace creator's stub `deploy_campaign` with a real call to `deploy.deploy_full_campaign`; fix budget guardrail math; fix retry exception type.

## Key Insights
- `creator.deploy_campaign` (lines 129-152) prints "Would deploy", passes `client=None`, returns True unconditionally → **success is a lie**.
- `deploy.deploy_full_campaign` is fully implemented (real GoogleAdsClient calls) but **never called** (dead code).
- **Budget-math bug** (`creator.run_budget_guardrails` lines 69-74): `total_monthly = get_total_monthly_budget(db) + (daily_budget*30)` then `max_daily_total = total_monthly/30*2`. Since the proposed campaign's monthly is added to the numerator, the cap scales with the proposal → **guardrail never trips**. Fix: cap must EXCLUDE proposed campaign. Use env const `MONTHLY_BUDGET` as the ceiling (Q3).
- **Retry bug** (`deploy.retry_with_backoff` line 286): catches `exceptions.TooManyRequests`. Google Ads rate limits surface as `GoogleAdsException` with `TOO_MANY_REQUESTS`/429, not `TooManyRequests`. Retry never fires on real rate limits.

## Requirements
### Functional
- `creator.deploy_campaign` must init `GoogleAdsClient.load_from_env()`, read `customer_id` from env, call `deploy.deploy_full_campaign(client, customer_id, plan, variations)`, and report success ONLY when `result["success"]` is True.
- Budget guardrail cap must not include the proposed campaign.
- Retry must catch the actual Google Ads rate-limit exception.
### Non-functional
- No silent mock (Phase 05 handles explicit `--mock`). Missing creds → exception.
- google-ads-python v28 API enum access (current code uses v17 paths — migrate).

## Architecture
```
creator.main()
  → run_budget_guardrails(db, daily_budget)   [fixed math]
  → approval gate (Phase 03)
  → deploy_campaign(plan, variations)
       → GoogleAdsClient.load_from_env()
       → deploy.deploy_full_campaign(client, customer_id, plan, variations)
            → create_campaign / ad_group / keywords / ads (with retry)
       → return result["success"]
  → save campaign_id (real GoogleAds resource name) to _store
```

## Interfaces
**Consumes:**
- `deploy.deploy_full_campaign(client, customer_id: str, plan: dict, variations: list[dict]) -> dict` (returns `{success, campaign_resource_name, ...}`)
- env: `GOOGLE_ADS_CUSTOMER_ID`, `GOOGLE_ADS_CLIENT_ID/SECRET/DEVELOPER_TOKEN/REFRESH_TOKEN`, `MONTHLY_BUDGET`

**Produces:**
- `creator.deploy_campaign(plan: dict, approved_variations: list[dict]) -> bool` (True only on real success)
- `_store.save_campaign(campaign_data)` called with real `campaign_resource_name`

## Related Code Files
- **Modify**: `scripts/creator.py` (deploy_campaign, run_budget_guardrails)
- **Modify**: `scripts/deploy.py` (retry_with_backoff exception, v17→v28 enum migration)
- **Read-only**: `scripts/policy_check.py`, `scripts/_store.py`

## Implementation Steps
1. `deploy.retry_with_backoff`: catch `GoogleAdsException`; inspect `e.error.code` for rate-limit; also catch generic retryable. Verify against google-ads v28 docs.
2. `deploy.py`: migrate enum access from `client.enums.XEnum.Y` (v17) to v28 `client.enums.XEnum.Y` or `google.ads.googleads.enums`. Run against test account to confirm.
3. `creator.run_budget_guardrails`: cap = `MONTHLY_BUDGET` env (default 500) / 30 * 2. Compare `get_total_existing_daily_budget(db) + daily_budget` vs cap. Remove self-inclusion.
4. `creator.deploy_campaign`: load client from env, get customer_id, call `deploy_full_campaign`, return `result["success"]`.
5. Wire real `campaign_resource_name` into `save_campaign` (replaces synthetic ID at L4 partially — full L4 fix deferred).

## Todo List
- [ ] Fix budget guardrail math (env const cap)
- [ ] Fix retry exception type + verify against v28
- [ ] Migrate deploy.py enum paths v17→v28
- [ ] Wire creator→deploy_full_campaign
- [ ] Pass real campaign_resource_name to save_campaign
- [ ] Test against Google Ads test account

## Success Criteria
- `creator.py --plan data/X.json` creates a real campaign on Google Ads **test account** (visible in UI).
- Budget guardrail rejects a plan exceeding `MONTHLY_BUDGET/30*2` cap (test with high `--budget`).
- Retry fires on simulated rate-limit (force 429 in test).

## Risk Assessment
- **High** — Google Ads API version drift (v17→v28 enum changes). **Mitigation**: verify with context7 docs before coding; test on test account first; pin `google-ads==28.1.0`.
- **Medium** — OAuth refresh token may be expired. **Mitigation**: Phase 09 setup checklist; verify token in test run.

## Security Considerations
- Credentials loaded from env file (not committed). `google-ads.env` in `.gitignore` (verify).
- `MONTHLY_BUDGET` cap is the spend safety net — must be honest value.

## Next Steps
- Depends on Phase 01 (no crash). Enables Phase 03 (approval gate), Phase 05 (rollback).
