# Phase 09 — Sync SKILL.md + Docs + End-to-End Verification

## Context Links
- Plan: [`plan.md`](plan.md)
- Touches: all findings (docs accuracy), M3 (SKILL.md CLI fix)

## Overview
- **Priority**: P2
- **Status**: pending
- **Effort**: 4h
- Reconcile SKILL.md claims with fixed reality; pin dependencies; end-to-end verify on real Google Ads test account + live Cloudflare Workers.

## Key Insights
- SKILL.md currently overstates capabilities ("web search + LLM", "deploys via Google Ads API", "Mock client for development"). After fixes, align doc to truth: real research, real deploy, async approval gate, no silent mock.
- M3: fix cron command `monitor.py full` → `monitor.py --mode full` (line 326, 336).
- Pin `google-ads` version (H9 from parent plan) — `google-ads==28.1.0`.
- Add `SERPER_API_KEY` to env example (Phase 04).
- Verification MUST be on real infra (per CLAUDE.md: no mocks to pass).

## Requirements
### Functional
- SKILL.md reflects actual behavior (no false claims; mock only behind `--mock`).
- Cron commands correct.
- `requirements.txt` pinned.
- `google-ads.env.example` complete + accurate.
### Non-functional
- End-to-end run on Google Ads test account + live Workers documented with screenshots/output.

## Architecture
N/A (docs + verification).

## Interfaces
**Consumes:** all fixed scripts.
**Produces:** accurate docs.

## Related Code Files
- **Modify**: `skills/research/google-ads/SKILL.md`
- **Modify**: `skills/research/google-ads/google-ads.env.example`
- **Create**: `skills/research/google-ads/requirements.txt`
- **Update**: `docs/project-changelog.md`, `docs/development-roadmap.md` (per documentation-management rules)

## Implementation Steps
1. SKILL.md: rewrite "Research Capabilities" (real web+LLM), "Campaign Creation" (async approval gate, no input()), "Monitoring" (correct cron `--mode full`), remove "Mock client for development" misleading line → state `--mock` explicit only.
2. SKILL.md: add "Headless / Telegram Approval" section explaining async gate (Phase 03).
3. `requirements.txt`: `google-ads==28.1.0`, `requests>=2.31`.
4. `google-ads.env.example`: add `SERPER_API_KEY=`, confirm `GOOGLE_ADS_CUSTOMER_ID` vs `LOGIN_CUSTOMER_ID` distinction documented.
5. **E2E verification matrix** (real infra):
   a. `research.py --niche X` → real JSON (no placeholders).
   b. `creator.py --plan X.json` → Telegram approval request received.
   c. `creator.py --approve <uuid> --indices 1,3,5` → campaign visible in Google Ads test account UI.
   d. Force ad-group failure → rollback removes campaign (Phase 05).
   e. `monitor.py --mode sync` → metrics appear; `--mode detect` no crash (Phase 01/07).
   f. `sync_to_d1.py` → D1 receives metrics+anomalies+campaigns (Wrangler query).
   g. Dashboard shows synced data.
6. Update changelog + roadmap.

## Todo List
- [ ] Rewrite SKILL.md (capabilities, approval gate, cron commands)
- [ ] Create requirements.txt (pinned)
- [ ] Update google-ads.env.example (SERPER_API_KEY, customer_id notes)
- [ ] E2E verify research (real data)
- [ ] E2E verify creator + approval + deploy (test account)
- [ ] E2E verify rollback
- [ ] E2E verify monitor + sync (D1 receives)
- [ ] Update changelog + roadmap

## Success Criteria
- SKILL.md contains no unverifiable claims; every CLI example matches actual flags.
- Full pipeline (research→approve→deploy→monitor→sync→dashboard) runs on real Google Ads test account + live Workers with human-verified output.
- `pip install -r requirements.txt` reproduces exact env.

## Risk Assessment
- **Medium** — E2E may surface integration gaps not caught per-phase. **Mitigation**: this is the catch-all; time-box; log blockers.
- **Low** — docs drift. **Mitigation**: single source (SKILL.md) + changelog.

## Security Considerations
- No secrets in SKILL.md/examples (placeholders only). Confirm `.gitignore` covers `google-ads.env`, `data/`.

## Next Steps
- Final phase. On completion, plan status → completed; update roadmap to mark google-ads skill production-ready.
