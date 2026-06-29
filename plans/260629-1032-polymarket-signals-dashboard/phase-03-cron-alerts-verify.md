# Phase 03 — Cron Wiring (no_agent) + Failure Alerts + Verify/Monitor

## Context
- Parent: [plan.md](plan.md). Depends: phase-02 (publish works).
- Scenario criticals: C2 (no_agent=True), C4 (silent failure → alert). High: read/write timing (#7/#8), disk/token (#22/#23/#24).
- Cron model reference: parent plan F-01 (Hermes cron two modes: `no_agent=True` = script-only; default = agent one-shot).

## Overview
Schedule `publish_dashboard.py` to run shortly after each scan via Hermes cron in
**`no_agent=True` mode** (script-only — no LLM ingests prediction data or deploy token).
Any failure (generate, deploy, token, disk) alerts Telegram — **never silent** (C4, F-09 cousin).
Then end-to-end verify + set up ongoing monitoring.

## Key Insights
- **`no_agent=True` is mandatory (C2/F-01)**: the publish script touches the SQLite (with
  prediction data) and the Cloudflare token. In default cron mode the agent receives script
  stdout/context as a one-shot — that would expose prediction data + token-adjacent context to
  the LLM. `no_agent=True` runs the script verbatim, no agent, no tools. Pin this.
- **Timing vs scan**: scan cron is `0 0,12 * * *`; publish at `5 0,12 * * *` (5-min offset).
  Scan must be `status='done'` before publish reads it (phase-00 already filters). If scan
  overruns 5 min, publish reads the prior completed scan — acceptable, no partial data.
- **Read-while-write (C7)**: phase-00 `mode=ro` WAL snapshot means publish can even overlap an
  active scan safely; the 5-min offset is just cleanliness.
- **Failure visibility**: Hermes cron `no_agent=True` prints stdout verbatim but does NOT alert
  on non-zero exit by itself → the script must push its own Telegram alert on failure (C4),
  reusing the skill's `_alert` delivery path.

## Requirements
- **Functional**: cron runs publish after each scan; failures alert Telegram.
- **Non-functional**: `no_agent=True`, idempotent, no data/token reaches an agent context.

## Architecture
```
Hermes cron job: "Polymarket Dashboard Publish"
  schedule: "5 0,12 * * *"   # 5 min after scan
  no_agent: true              # C2 — script only, no LLM context
  command: python3 ~/.hermes/skills/polymarket-signals/scripts/publish_dashboard.py
  env: HERMES_HOME, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID (from hermes.env)

publish_dashboard.py failure → _alert delivery → Telegram (C4)
```

## Related Code Files
- **Reuse**: `publish_dashboard.py` (phase-02), `_alert` delivery path.
- **Operate**: Hermes cron (`hermes cron add/list`), `~/.hermes/hermes.env`.

## Implementation Steps
1. Confirm `publish_dashboard.py` alerts on ALL failure modes (generate fail, wrangler fail,
   token missing, disk full) via the skill's Telegram delivery — wrap top-level in try/except
   that ALWAYS alerts before `sys.exit(1)` (C4, #22/#23/#24).
2. Add cron job (Hermes cron CLI):
   - name `Polymarket Dashboard Publish`, schedule `5 0,12 * * *`, **`no_agent=true`**,
     command `python3 <skill>/scripts/publish_dashboard.py`.
   - Verify with `hermes cron list` → job `active` + `no_agent` flag set (C2).
3. **End-to-end verify**:
   - Trigger publish manually (`python3 publish_dashboard.py`) → dashboard updates at URL.
   - Force a failure (e.g. unset token) → confirm Telegram alert arrives (C4).
   - Incognito visit URL → Access gate (confirms C3 still holds post-cron).
   - Confirm scan→publish cadence: after next `0 0,12` scan, dashboard `last scan` advances.
4. **Monitoring checklist** (fold into parent plan's weekly check):
   - `hermes cron list` weekly → publish job `active`.
   - Dashboard `last scan ts` advances twice daily (stale = publish or scan broke).
   - Resolution health panel: disputed count watched (surfaces F-06 UMA issues).
   - Telegram: any publish-failure alert = investigate immediately.
5. **Skill doc update**: add a `## Dashboard` section to `skills/research/polymarket-signals/SKILL.md`
   (URL, how to publish manually, cron schedule, Access login). Docs impact: minor.

## Todo
- [ ] `publish_dashboard.py` top-level try/except → always alert before exit (C4)
- [ ] Cron job added: `5 0,12 * * *`, `no_agent=true` (C2)
- [ ] Verify `hermes cron list` shows active + no_agent
- [ ] E2E: manual publish updates URL; forced-failure alerts Telegram
- [ ] Incognito Access check post-cron
- [ ] Monitoring checklist + SKILL.md `## Dashboard` section

## Success Criteria
- Cron job active, `no_agent=true` confirmed (C2).
- After a real scan, dashboard auto-updates within ~5 min, twice daily.
- Forced failure → Telegram alert within the cron tick (C4). No silent fails.
- Access still gates the URL after cron-driven deploys (C3).
- Weekly monitoring checklist documented.

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| Cron runs in default (agent) mode → data/token to LLM | Crit | Pin `no_agent=true`; verify flag in `cron list` (C2) |
| Silent publish failure (F-09 cousin) | Crit | Script-level alert on every failure path (C4) |
| Scan overruns publish offset | Med | `mode=ro` snapshot safe; reads prior done-scan only |
| Cron env missing token | High | preflight check + alert (C8/#22) |
| Disk full mid-generate | Med | generate handles IOError → alert (#24) |

## Security
- C2 + C4 are this phase's security core.
- Confirm no agent session ever receives prediction data or token context.

## Next Steps
- Done. Dashboard live, auto-published, monitored.
- Re-evaluation tie-in: when parent plan's ~2026-08-01 Brier checkpoint lands, the dashboard
  already visualizes the data needed for the go/no-go decision.
