# Phase 06 — Fix D1 Sync Payload + Lock + Dedup

## Context Links
- Plan: [`plan.md`](plan.md)
- Findings: H4 (`sync-status.json` no lock → race), H5 (`get_unsynced_campaigns` resends all active every run)
- Resolves: Q2 (Workers `/api/sync` payload shape mismatch)

## Overview
- **Priority**: P2 (data integrity)
- **Status**: pending
- **Effort**: 3h
- Fix the payload shape Hermes sends vs what Workers accepts; add file lock on status writes; stop resending already-synced campaigns.

## Key Insights
- **Q2 CONFIRMED**: Workers `infrastructure/src/sync.js` destructures `const { metrics, leads, campaigns, ad_groups, ads, keywords } = body`. Hermes sends `{metrics, anomalies, campaigns, sync_type}`. **`anomalies` is ignored by Workers** — anomalies never reach D1. `leads/ad_groups/ads/keywords` never sent → those D1 tables never populate.
- H4: `sync-status.json` written without `fcntl.flock`. Cron overlap → lost updates / corrupted JSON.
- H5: `get_unsynced_campaigns` selects `WHERE status='active'` with no `synced_to_d1` filter → every sync resends ALL active campaigns. Payload grows unbounded; rate-limit (1 req/min) trips.

## Requirements
### Functional
- Sync payload must include the fields Workers expects: `metrics, leads, campaigns, ad_groups, ads, keywords` (or extend Workers to accept `anomalies` — decide per KISS).
- Anomalies must reach D1: either add `anomalies` handling to `sync.js` OR route anomalies via separate endpoint. **Recommend**: add `anomalies` to `sync.js` (single endpoint, simpler).
- `get_unsynced_campaigns` must filter on a sync flag.
- `sync-status.json` writes guarded by `fcntl.flock`.
### Non-functional
- Campaigns once synced not resent unless changed (`updated_at` > last sync).

## Architecture
```
sync_to_d1.run_sync (with flock):
  get unsynced metrics/anomalies/campaigns (campaigns: only changed)
  build payload {metrics, anomalies, campaigns, leads, ad_groups, ads, keywords}
  POST /api/sync
  on success: mark_synced (metrics, anomalies, campaigns)
sync.js:
  accept anomalies → upsertAnomaly (new db-helper)
```

## Interfaces
**Consumes:**
- Workers schema (D1 tables: campaigns, ad_groups, ads, keywords, daily_metrics, leads, anomaly_log)

**Produces:**
- `sync_to_d1.get_unsynced_campaigns() -> list` (only `synced_to_d1=0 OR updated_at > last_sync`)
- `sync_to_d1.mark_synced(...)` now also marks campaigns
- Workers `handleSync` accepts `anomalies` array

## Related Code Files
- **Modify**: `scripts/sync_to_d1.py` (payload, get_unsynced_campaigns filter, flock)
- **Modify**: `infrastructure/src/sync.js` (accept anomalies)
- **Modify**: `infrastructure/src/db-helpers.js` (add `upsertAnomaly`)
- **Read-only**: `_store.py` (campaigns schema — add `synced_to_d1` column if missing)

## Implementation Steps
1. Audit `_store.py` campaigns table: ensure `synced_to_d1 INTEGER DEFAULT 0` + `updated_at` columns exist (migration if not).
2. `get_unsynced_campaigns`: `WHERE synced_to_d1 = 0 OR updated_at > ?last_sync`.
3. `build_sync_payload`: add `anomalies` key (already built) — keep; verify `sync_type` doesn't break Workers (ignored — fine).
4. `mark_synced`: add campaigns ids to UPDATE.
5. `log_sync_failure` + any status write: wrap in `fcntl.flock` context manager.
6. `sync.js`: destructure `anomalies`; loop `upsertAnomaly(env.DB, anomaly)`. Add `upsertAnomaly` to db-helpers (INSERT OR REPLACE into anomaly_log-equivalent D1 table — verify D1 has it).
7. Verify D1 `anomaly_log` table exists (parent plan phase-02 schema); create migration if missing.

## Todo List
- [ ] Audit/migrate campaigns table sync columns
- [ ] Fix get_unsynced_campaigns filter
- [ ] Add flock to status writes
- [ ] Extend sync.js to accept anomalies + upsertAnomaly
- [ ] mark_synced marks campaigns
- [ ] Test sync against live Workers; verify D1 receives anomalies + no resend

## Success Criteria
- After successful sync, `get_unsynced_campaigns` returns empty (until a campaign changes).
- Anomalies appear in D1 `anomaly_log` (query via Wrangler).
- Concurrent cron runs do not corrupt `sync-status.json` (flock test).
- Payload accepted by live Workers (HTTP 200, `{success:true}`).

## Risk Assessment
- **Medium** — D1 schema may lack `anomaly_log` table. **Mitigation**: verify via `wrangler d1 execute`; migration step included.
- **Low** — flock on NFS (not relevant — local VPS ext4).

## Security Considerations
- `X-Hermes-Secret` already validated in sync.js (verified). Keep.

## Next Steps
- Depends on Phase 01. Verified live in Phase 09.
