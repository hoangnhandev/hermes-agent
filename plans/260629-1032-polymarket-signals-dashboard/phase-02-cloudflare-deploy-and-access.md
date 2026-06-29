# Phase 02 — Cloudflare Pages Deploy + Access + Token Hygiene

## Context
- Parent: [plan.md](plan.md). Depends: phase-01 (`dist/dashboard.html`).
- Scenario criticals: C3 (Access before deploy), C8 (token hygiene). High: wrangler pin (#31/#33), preview URLs (#29), deploy race (#9).
- Deployment env: `docs/plans/hermes-server-deployment-guide.md` (withly-server, Hermes native, `~/.hermes/hermes.env`).

## Overview
Wire static `dist/` → Cloudflare Pages via `wrangler` direct upload (no git, no build step
on Cloudflare). Put Cloudflare Access (Zero Trust, email OTP) in front. Token scoped to the
minimum. **Access configured BEFORE first public deploy** (C3) — otherwise all prediction
data is public on a `.pages.dev` URL.

## Key Insights
- **Direct upload, not git**: `wrangler pages deploy dist/ --project-name=...` pushes a
  pre-built artifact. Avoids committing prediction data into a git repo's history (the
  data is embedded in the static HTML). (plan.md constraint)
- **Access covers the domain + all deployments**: a Cloudflare Access application on the
  Pages hostname protects production AND preview deployment URLs. Verify preview URLs are
  covered (#29) — otherwise old deployment URLs leak data.
- **Token = the blast radius**: a broad `Account:Edit` token can wreck the account. Scope to
  `Cloudflare Pages — Edit` for ONE project. Read from env, never as CLI arg (visible in
  `ps`/cron logs) — wrangler reads `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` from env. (C8)
- **Data sensitivity is LOW** (signal-only: probabilities + Brier, no money/PII) — but Access
  is still good practice and free.

## Requirements
- **Functional**: `publish_dashboard.py` runs generate then deploys; idempotent.
- **Non-functional**: atomic (generate→temp→close→deploy, #9), no secret in argv/logs,
  preflight (wrangler present + authed), exit non-zero + surfaced on any failure.

## Architecture
```
scripts/publish_dashboard.py   # generate_dashboard → wrangler pages deploy → result
  ├─ preflight()               # wrangler in PATH? token in env? dist exists?
  ├─ run_generate()            # subprocess generate_dashboard.py (atomic write)
  ├─ wrangler_deploy()         # subprocess wrangler, env-borne token, capture stderr
  └─ alert_on_failure(err)     # reuse _alert delivery path → Telegram (C4)
```
Cloudflare side (manual, once):
- Pages project `polymarket-signals-dashboard` (direct-upload, no build cmd).
- Access app: hostname `*.pages.dev`, email-OTP policy → your email.

## Related Code Files
- **Create**: `scripts/publish_dashboard.py`.
- **Reuse**: `generate_dashboard.py` (phase-01), `_alert` delivery path (Telegram).
- **Config**: add to `~/.hermes/hermes.env` (NOT git): `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DASHBOARD_CF_PROJECT`, `DASHBOARD_PUBLIC_URL`.

## Implementation Steps
1. **Manual (do FIRST — C3)**: in Cloudflare Zero Trust → Access → Applications, create app
   for the Pages domain (create placeholder project first if needed). Email-OTP policy to your
   address. Note: this must exist before the URL carries data.
2. **Manual**: create Pages project `polymarket-signals-dashboard` (framework: none, direct upload).
3. **Token (C8)**: Cloudflare dashboard → My Profile → API Tokens → "Edit Cloudflare Workers"
   template customized to **Pages:Edit, one project, one zone if needed**. Store in
   `~/.hermes/hermes.env` as `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`. `chmod 600`.
4. **Install wrangler on VPS** (pinned): `npm i -g wrangler@<pin>` (or `npx wrangler@<pin>`).
   Record pinned version in this phase + `publish_dashboard.py` preflight.
5. `publish_dashboard.py`:
   - `preflight()`: check `wrangler --version` matches pin (warn/exit if mismatch, #31/#33);
     check `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` present (exit + alert if not).
   - `run_generate()`: subprocess `generate_dashboard.py`; fail → alert + exit.
   - `wrangler_deploy()`: `subprocess.run(["wrangler","pages","deploy","dist","--project-name",proj])`
     with env inherited (token NEVER in argv). Capture stdout/stderr; parse deployment URL.
   - On any `returncode!=0` → `alert_on_failure()` → exit 1 (C4).
   - Success → print deployed URL + timestamp.
6. **Atomicity (#9)**: generate writes temp→`os.replace` (phase-01) BEFORE wrangler reads
   `dist/`. Wrangler reads only after generate exits 0.
7. Local dry-run: `wrangler pages deploy dist/ --project-name=... --dry-run` to validate
   upload payload without publishing.

## Todo
- [ ] Cloudflare Access app created (email-OTP) — BEFORE first real deploy (C3)
- [ ] Pages project created (direct upload, no build)
- [ ] Token scoped Pages:Edit 1 project; in hermes.env chmod 600 (C8)
- [ ] wrangler pinned version installed on VPS
- [ ] `publish_dashboard.py`: preflight + generate + wrangler + alert-on-fail (C4)
- [ ] Atomic generate→deploy (#9)
- [ ] `--dry-run` upload validation

## Success Criteria
- `python3 publish_dashboard.py` deploys `dist/` to Cloudflare Pages; prints live URL.
- Visiting URL in incognito → Cloudflare Access login (NOT the dashboard). (C3)
- After auth → dashboard renders. Preview/old deployment URLs ALSO gated. (#29)
- Kill/empty the token → publish fails AND Telegram alert fires. (C4/C8)
- No token in `ps aux` or cron journal during a deploy.

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| Access not configured before deploy → data public | Crit | Manual step #1 FIRST; verify incognito (C3) |
| Token too broad / leaked | Crit | Scoped token, env-only, chmod 600, no argv (C8) |
| Preview deployment URLs ungated | High | Verify Access covers `*.pages.dev` deploys (#29) |
| Wrangler version drift breaks deploy | High | Pin + preflight version check (#31/#33) |
| Deploy race / partial upload | High | Atomic temp→replace before wrangler reads (#9) |

## Security
- C3 + C8 are the security core of this phase.
- Token rotation procedure documented (revoke + replace in hermes.env).
- Access audit: who/when logged in visible in Zero Trust logs (#11 light compliance).

## Next Steps
- → phase-03: Hermes cron (`no_agent=True`) to run publish after each scan + alerts + monitoring.
