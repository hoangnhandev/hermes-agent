---
title: "Polymarket Signals Calibration Dashboard"
description: "Static HTML dashboard on Cloudflare Pages visualizing calibration/Brier/edge from the polymarket-signals SQLite store."
status: complete
priority: P3
effort: ~5-6h
branch: main
approach: static-html-cloudflare-pages
extends: [20260626-polymarket-signal-bot]
depends_on_skill: skills/research/polymarket-signals
tags: [polymarket, dashboard, visualization, cloudflare, calibration]
created: 2026-06-29
---

# Polymarket Signals Calibration Dashboard — Plan

## Overview

Static HTML dashboard visualizing the calibration data of the (MVP-complete)
`polymarket-signals` skill. A stdlib-first Python generator reads the existing
SQLite store (read-only), emits a dark Plotly dashboard, and a cron job
publishes it to **Cloudflare Pages** (global CDN, offloads VPS) behind
**Cloudflare Access** (email OTP). Signal-only data, low sensitivity.

Design source: in-conversation brainstorm + `/ck:scenario` (44 scenarios,
8 Critical). Self-contained below; see phase files for detail.

## Architecture

```
withly-server (VPS, Hermes native):
  [cũ]  Hermes cron → predict.py → store.py → SQLite (~/.hermes/polymarket_signals.db)
  [MỚI] cron (no_agent=True, after scan) → generate_dashboard.py → dist/dashboard.html
  [MỚI]                                 → publish_dashboard.py → wrangler pages deploy
Cloudflare Pages (global CDN):
  dashboard.html ← Cloudflare Access (email OTP) ← public URL
```

Data = batch (cron scan 2×/day `0 0,12` + resolution `0 3`). Static regen after
each scan = correct freshness. **NOT real-time** → live web app = over-engineering.

## Global Constraints

- **Read-only**: dashboard never writes SQLite. Opens own `mode=ro` WAL connection.
  **MUST NOT use `_store_core._r()`** (it `sys.exit(1)` on flock contention → dies when
  scan is writing). See phase-00.
- **Cron exec model**: publish job **MUST run `no_agent=True`** (script-only). No agent
  ingests prediction data or deploy token context. (scenario #30 / F-01)
- **Cron timing**: fire AFTER scan completes. Only count scans `status='done'`.
- **Stdlib-first**: generator = stdlib only (sqlite3/json/html/string). Plotly via CDN
  `<script>`, **pinned version**. Wrangler = separate CLI.
- **Zero new pip dep** in generator. New external CLI deps (wrangler) pinned + preflight.
- **KISS/YAGNI/DRY**: reuse `_store_reads`, `_paths`, `_alert` delivery path.
- **No secrets in HTML/HTML/HTML**: dashboard = probabilities + Brier only.
- **`code-standards.md` not found in docs/** → follow existing skill conventions:
  kebab-case filenames, <200 lines/file, descriptive comments, stdlib-first.
- **Naming**: kebab-case. Build artifact `dashboard/dist/` gitignored (deployed, not committed).

## Phases

| # | Phase | Effort | Depends | File |
|---|---|---|---|---|
| 00 | Generator core + metrics (read-only conn) | 1.5h | — | [phase-00](phase-00-generator-and-metrics.md) |
| 01 | HTML template + 7 panels + Plotly (XSS/empty-state/scale) | 2h | 00 | [phase-01](phase-01-template-and-panels.md) |
| 02 | Cloudflare Pages deploy + Access + token hygiene | 1.5h | 01 | [phase-02](phase-02-cloudflare-deploy-and-access.md) |
| 03 | Cron wiring (no_agent) + failure alerts + verify/monitor | 1h | 02 | [phase-03](phase-03-cron-alerts-verify.md) |

## Success Criteria

- Dashboard renders from current SQLite with zero predictions (empty state) AND with data.
- All untrusted text (questions/rationale) HTML-escaped — no XSS.
- Calibration/Brier computed on `outcome_int IS NOT NULL` only.
- `wrangler pages deploy` succeeds; site live behind Cloudflare Access (blocked without auth).
- Publish cron runs `no_agent=True`; any failure alerts Telegram (no silent fail).
- Generator reads via `mode=ro` — never blocks/kills the scan writer.

## 🔴 8 Critical (from /ck:scenario) — mitigated in phases

| # | Critical | Phase |
|---|---|---|
| C1 | XSS via untrusted question/rationale in HTML | 01 |
| C2 | Publish cron MUST `no_agent=True` (F-01) | 03 |
| C3 | Cloudflare Access configured BEFORE first deploy; cover preview URLs | 02 |
| C4 | Silent deploy failure → Telegram alert (F-09 cousin) | 03 |
| C5 | Brier/calibration on resolved only (`outcome_int IS NOT NULL`) | 00 |
| C6 | Empty DB / zero-resolved → correct empty state, no crash/rubbish curve | 00+01 |
| C7 | Read-while-write → `mode=ro` WAL, only scans `status='done'` | 00 |
| C8 | Token scope min (Pages:Edit 1 project), from env, no CLI arg/log | 02 |

## Out of Scope (locked)

- Real-time/live web app, server process, auth backend (static only).
- Real-money/trading/positions (skill stays signal-only).
- Writing to SQLite from dashboard.
- Calibration-feedback loop injection into predictor (gated phase-03 of parent plan).

## Dependencies

- Parent plan `20260626-polymarket-signal-bot` (COMPLETE MVP) — provides SQLite schema + skill.
- `withly-server` Hermes native + cron + Telegram gateway (per `docs/plans/hermes-server-deployment-guide.md`).
- Cloudflare account (free): Pages + Access (Zero Trust ≤50 users).
- `wrangler` CLI on VPS (pinned), `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` in `~/.hermes/hermes.env`.

## Risk Assessment (High-severity highlights — full list in phase files)

| Risk | Sev | Mitigation |
|---|---|---|
| Plotly CDN blocked/version drift | High | Pin version; optional local bundle; `<noscript>` fallback |
| Duplicate predictions double-count calibration (F-03) | High | De-dup by `condition_id` (latest) in metric query |
| outcome_int≠0/1 or disputed (F-06) | High | Exclude outliers; bucket 'disputed' in resolution health |
| Wrangler missing/wrong version on VPS | High | Preflight check + pin |
| Deploy race (generate writing while wrangler reads) | High | Atomic: generate→temp→close→deploy |
| Calibration curve on <10 resolved (F-14 cousin) | High | Show n + warn "insufficient data" |
