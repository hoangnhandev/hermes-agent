# google-ads Skill + Ads Copilot — Deploy Guide

End-to-end deploy workflow: sync code to the VPS, deploy the Cloudflare Worker +
dashboard, run the skill runtime on cron. This is the **operational** companion
to `SKILL.md` (which documents usage).

## Architecture

```
┌─ LOCAL (dev machine) ──────────────────────────────────────────────┐
│  git repo (origin: hoangnhandev/hermes-agent.git)                   │
│    skills/research/google-ads/   ← the skill (this dir)             │
│    plans/260629-1125-hermes-ads-copilot/{infrastructure,dashboard}  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ git push origin main
                           ▼
┌─ VPS  contabo_withly_vn  (user: withlyvn) ──────────────────────────┐
│                                                                     │
│  ~/hermes-agent/               ← git checkout (git pull to update)  │
│    skills/research/google-ads/                                      │
│      scripts/*.py            ← monitor/optimize/deploy/...          │
│      .venv/                  ← google-ads lib installed             │
│      google-ads.env          ← SECRETS (gitignored, VPS-only)       │
│      data/campaigns-local.db ← local SQLite source of truth         │
│      data/ads-*.sh logs                                             │
│                                                                     │
│  ~/ads-copilot-deploy/        ← Worker staging (rsync target, NOT   │
│    infrastructure/              git — avoids git divergence)        │
│      .dev.vars               ← SECRETS (gitignored)                 │
│      wrangler.toml + src/     ← `wrangler deploy` runs here         │
│    dashboard/                ← static assets (same origin)          │
│                                                                     │
│  ~/.hermes/hermes.env         ← CLOUDFLARE_API_TOKEN + ACCOUNT_ID   │
│  ~/.hermes/scripts/ads-*.sh   ← cron wrappers (source env + venv)   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ wrangler deploy
                           ▼
┌─ Cloudflare ───────────────────────────────────────────────────────┐
│  Worker  ads-copilot-api  →  https://ads-copilot.withly.org         │
│    - /api/sync        (skill → D1, X-Hermes-Secret auth)            │
│    - /api/anomalies   (dashboard read, JWT cookie auth)             │
│    - /api/{metrics,leads,form-leads,keywords,budget}                │
│    - static assets    (dashboard SPA, same origin)                  │
│  D1      ads_copilot  (72edf6dd-5fb1-4684-a017-8eadc422899c)        │
└─────────────────────────────────────────────────────────────────────┘
```

**Two deploy surfaces:** (1) the skill runtime on the VPS (cron-driven), and
(2) the Cloudflare Worker + dashboard (user-facing). They share D1 via
`/api/sync`. The skill is the source of truth (local SQLite); D1 is a replica.

## Prerequisites (already in place — verify, don't recreate)

| Item | Location | Notes |
|---|---|---|
| SSH access | `contabo_withly_vn` (`~/.ssh/contabo_withly_vn`) | host `213.136.79.25` |
| VPS git checkout | `~/hermes-agent` | remote = origin; `git pull --ff-only` |
| Skill venv | `~/hermes-agent/skills/research/google-ads/.venv` | has `google-ads` lib |
| `google-ads.env` | skill dir, **gitignored** | real Developer Token + Refresh Token + Customer IDs + MONTHLY_BUDGET (VND) |
| CF creds | `~/.hermes/hermes.env` | `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` (must `export`) |
| `.dev.vars` | `~/ads-copilot-deploy/infrastructure/` | `DASHBOARD_PASSWORD`, `JWT_SECRET`, `HERMES_SYNC_SECRET` (gitignored) |
| Cron wrappers | `~/.hermes/scripts/ads-{monitor,report,optimize}.sh` | installed in crontab |

> **Never** commit `google-ads.env` or `.dev.vars` — both are gitignored and hold
> live tokens. The VPS copies are the source of truth for secrets, NOT the repo.

## Deploy workflow

### A. Skill code (VPS runtime)

The VPS `~/hermes-agent` is a checkout of the same repo → `git pull` updates it.

```bash
ssh contabo_withly_vn '
  cd ~/hermes-agent && git pull --ff-only origin main
'
```

Untracked files on the VPS (`hermes.log`, `*.env.bak-*`, `data/`, `.venv/`) do
not conflict with the pull. **Do NOT rsync the local `google-ads.env` over the
VPS one** — the VPS env is the live source of truth (real Developer Token).

If a skill dependency changed, rebuild the venv:
```bash
ssh contabo_withly_vn 'cd ~/hermes-agent/skills/research/google-ads && \
  ./.venv/bin/pip install -r requirements.txt 2>/dev/null || \
  echo "(no requirements.txt — install google-ads manually if needed)"'
```

### B. Worker + dashboard (Cloudflare)

The Worker is deployed **from the VPS staging dir** (not local, not the git
checkout directly) — rsync the checkout into staging first, then deploy.

```bash
ssh contabo_withly_vn '
  set -e
  # 1. rsync updated code (VPS checkout -> staging). No --delete: keeps .dev.vars.
  rsync -a ~/hermes-agent/plans/260629-1125-hermes-ads-copilot/infrastructure/ \
            ~/ads-copilot-deploy/infrastructure/
  rsync -a ~/hermes-agent/plans/260629-1125-hermes-ads-copilot/dashboard/ \
            ~/ads-copilot-deploy/dashboard/
  # sanity: secrets preserved + new files staged
  test -f ~/ads-copilot-deploy/infrastructure/.dev.vars && echo ".dev.vars OK"

  # 2. deploy (CF creds must be EXPORTED — hermes.env sets them non-exported)
  cd ~/ads-copilot-deploy/infrastructure
  source ~/.hermes/hermes.env
  export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID
  wrangler deploy
'
```

Expected tail: `Deployed ads-copilot-api triggers` + `ads-copilot.withly.org`.

### C. D1 schema changes (when a new table/column ships)

`wrangler deploy` does **not** run `schema.sql` migrations. Apply DDL manually.
`CREATE TABLE IF NOT EXISTS` is idempotent and safe to re-run.

```bash
ssh contabo_withly_vn '
  cd ~/ads-copilot-deploy/infrastructure
  source ~/.hermes/hermes.env && export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID
  # example: the anomalies table (wire 5)
  wrangler d1 execute ads_copilot --remote --command \
    "CREATE TABLE IF NOT EXISTS anomalies (detected_at TEXT NOT NULL, anomaly_type TEXT NOT NULL, entity_id TEXT, entity_name TEXT, metric_name TEXT NOT NULL, current_value REAL, baseline_value REAL, change_pct REAL, synced_at TEXT NOT NULL DEFAULT (datetime('\''now'\'')), PRIMARY KEY (detected_at, entity_id, anomaly_type));"
  # verify
  wrangler d1 execute ads_copilot --remote --command \
    "SELECT name FROM sqlite_master WHERE type='\''table'\'' ORDER BY name;"
'
```

> Adding a **column** to an existing D1 table needs `ALTER TABLE ... ADD COLUMN`
> (D1 has no `IF NOT EXISTS` for columns — guard with a PRAGMA check in the skill
> code, which the local SQLite path already does).

### D. Cron (already installed — verify)

```bash
ssh contabo_withly_vn 'crontab -l | grep ads'
```

Current schedule (UTC):
- `0 */6 * * *` — `ads-monitor.sh` (sync metrics: API → SQLite → D1; silent)
- `0 2 * * *`   — `ads-report.sh` (daily Telegram report)
- `30 2 1 * *`  — `ads-optimize.sh` (monthly optimization review)

Wrappers `cd` to the skill dir + run `./.venv/bin/python3 scripts/<x>.py`.

## Verify (post-deploy smoke tests)

```bash
ssh contabo_withly_vn '
  # 1. Worker live + route exists (401 = auth gate, NOT 404)
  curl -s -o /dev/null -w "/api/anomalies → HTTP %{http_code}\n" \
    https://ads-copilot.withly.org/api/anomalies

  # 2. Monitor pipeline (read-only — uses real Developer Token, no spend)
  cd ~/hermes-agent/skills/research/google-ads
  ./.venv/bin/python3 scripts/monitor.py --mode sync 2>&1 | \
    grep -iE "client init|Found .* campaign|Queried .* metrics|Detected .* anomal|D1 sync|Error"
'
```

**Expected on a fresh account:** `Found 0 active campaigns from API` (query
succeeds, no campaigns deployed yet) → auth + pipeline are healthy, awaiting the
first `creator --approve` deploy. `0 campaigns` is **not** an error.

Open the dashboard at `https://ads-copilot.withly.org` (login with
`DASHBOARD_PASSWORD`). The **Anomaly Alerts** panel reads `/api/anomalies`
(populates once a campaign has data + an anomaly fires).

## Rollback

- **Worker:** `wrangler rollback` from the staging dir (reverts to the previous
  version), or `git checkout <prev-sha> -- plans/260629-1125-hermes-ads-copilot/`
  locally → push → VPS `git pull` → rsync → `wrangler deploy`.
- **Skill:** `cd ~/hermes-agent && git checkout <prev-sha>` (cron picks up the
  old code on next run). No data loss — local SQLite is the source of truth.
- **D1 bad migration:** `DROP TABLE anomalies` and recreate, or restore from
  Cloudflare D1 backup. Anomalies are non-critical display data.

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `wrangler: set CLOUDFLARE_API_TOKEN` | hermes.env sets vars non-exported. Add `export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID` after `source`. |
| Monitor `Found 0 campaigns` | Normal if no campaign deployed. If campaigns exist in the UI → check `campaign.status='ENABLED'` + the child account `GOOGLE_ADS_CUSTOMER_ID` (not the MCC). |
| `INVALID_CUSTOMER_ID` / auth error | `google-ads.env` refresh token expired → re-run `scripts/get_refresh_token.py` (stdlib OAuth helper) on a machine with the client_secret JSON. |
| `/api/anomalies` 404 | Worker not redeployed after adding the route → redo step B. |
| Dashboard Anomaly panel empty | Either no anomalies yet (expected early) OR D1 `anomalies` table missing → step C. |
| Telegram anomaly ping missing | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` unset in `google-ads.env`; monitor logs locally + never blocks sync. |
| `MONTHLY_BUDGET` too low warning | Cap is VND-native; a USD placeholder (e.g. `500`) is read as 500 VND/mo. Set the real VND monthly budget. |

## Money-safety (invariants)

- **Monitor + optimize are read-only / recommend-only** — cron never spends.
- **Deploy (`creator --approve`) is the only spend path** — manual, guarded by
  `MONTHLY_BUDGET` cap + policy screening + interactive approval.
- **Negatives only block queries** — they reduce spend, never increase it.
- Verify these hold before any code change that touches `deploy.py`,
  `creator.py`, or `_budget_calc.py`.
