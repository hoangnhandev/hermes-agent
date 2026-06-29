---
title: "Fix google-ads Skill — Real Deploy + Research, Hardened Monitoring"
description: "Fix all code-review findings (CRITICAL/HIGH/MEDIUM) to take the google-ads skill from ~55% prototype to production: real Google Ads deploy, real research, async headless approval gate, hardened sync."
status: pending
priority: P1
effort: ~28h
branch: main
tags: [google-ads, hermes-skill, bugfix, hardening, google-ads-api, cloudflare-d1]
created: 2026-06-30
---

# Fix google-ads Skill — Implementation Plan

## Overview

Code review verdict: **PROTOTYPE-ONLY (~55% real)**. Deploy is a stub,
research is 100% mock, monitor crashes on anomaly path, sync sends a payload
shape the Workers endpoint ignores. This plan fixes all CRITICAL/HIGH/MEDIUM
findings so the skill can create a real campaign end-to-end.

Parent architecture plan: [`plans/260629-1125-hermes-ads-copilot/plan.md`](../260629-1125-hermes-ads-copilot/plan.md)

## Global Constraints

- **Real Google Ads API only** — no silent mock fallback. Missing creds = hard fail unless `--mock` explicit.
- **Headless execution** — skill runs via Hermes cron + Telegram (no TTY). `input()` blocked; approval gate is async (Telegram reply / pending-file).
- **Budget hard cap** — `MONTHLY_BUDGET` env const (default 500). `max_daily = MONTHLY_BUDGET/30*2`. Cap excludes proposed campaign. Unoverridable by LLM.
- **Local SQLite = source of truth** — D1 is replica. Sync failure alerts human, never silent.
- **Conventions** — kebab-case dirs, `_`-prefix utils, stdlib-first, **files <200 lines** (split `_store.py`, `monitor.py`), YAGNI/KISS/DRY.
- **Verification on real infra** — Google Ads test account + live Cloudflare Workers. No mock-and-claim.
- **google-ads-python pinned** — `google-ads==28.1.0` (v17 API enum paths in current code migrated).

## Phases

| # | Phase | Effort | Depends | Findings | File |
|---|-------|--------|---------|----------|------|
| 01 | Quick-win import/crash fixes | 1h | — | C1, C4 | [phase-01](phase-01-quick-win-import-fixes.md) |
| 02 | Wire creator → real deploy | 4h | 01 | C2, H2, H3, L1, budget-math | [phase-02](phase-02-wire-real-deploy.md) |
| 03 | Async headless approval gate | 3h | 02 | M6, design decision | [phase-03](phase-03-async-approval-gate.md) |
| 04 | Real research (web search + LLM) | 5h | — | C3 | [phase-04](phase-04-real-research.md) |
| 05 | Harden deploy client + rollback | 2h | 02 | H1, H2 | [phase-05](phase-05-harden-deploy-rollback.md) |
| 06 | Fix D1 sync payload + lock + dedup | 3h | 01 | H4, H5, Q2 | [phase-06](phase-06-fix-d1-sync.md) |
| 07 | Standardize monitor client + customer_id | 2h | 01 | M1, M2, M3, M5, L3 | [phase-07](phase-07-monitor-client-cleanup.md) |
| 08 | Refactor: split oversized files + DRY | 4h | 01 | M4 | [phase-08](phase-08-refactor-split-dry.md) |
| 09 | Sync SKILL.md + docs + verification | 4h | 01-08 | docs, all | [phase-09](phase-09-docs-verification.md) |

## Dependency Graph

```
01 (imports) ─┬─► 02 (deploy) ─┬─► 03 (approval gate)
              │                └─► 05 (rollback hardening)
              ├─► 06 (d1 sync)
              ├─► 07 (monitor client)
              └─► 08 (refactor split)
04 (research) ──────────────────────────── (independent, parallel w/ 01-08)
09 (docs+verify) ◄── all of 01-08
```

**Parallelizable:** 04, 06, 07, 08 run concurrently after 01. File ownership below prevents conflicts.

## File Ownership (no overlap)

| Phase | Owns (create/modify) |
|-------|----------------------|
| 01 | `_store.py` (import line), `sync_to_d1.py` (import line) |
| 02 | `creator.py`, `deploy.py` |
| 03 | `creator.py` (approval fns), new `approval_gate.py`, `telegram_notify.py` |
| 04 | `research.py`, new `_research_web.py`, `_research_llm.py` |
| 05 | `deploy.py` (rollback fns) |
| 06 | `sync_to_d1.py`, Workers `infrastructure/src/sync.js` |
| 07 | `monitor.py` |
| 08 | `_store.py` split → `_store.py`+`_store_monitoring.py`+`_store_anomaly.py`; delete `init_campaigns_db.py` |
| 09 | `SKILL.md`, `google-ads.env.example`, `requirements.txt`, docs/ |

## Success Criteria

1. `python3 scripts/monitor.py --mode full` runs without crash (C1/C4 fixed).
2. `creator.py` deploys a real campaign to a Google Ads **test account** (C2).
3. Approval flow works headless via Telegram (M6 resolved).
4. `research.py` returns real keyword/competitor data, not hardcoded mock (C3).
5. Missing creds → hard fail unless `--mock` (H1).
6. Partial deploy failure → cleanup, no orphan spending campaign (H2).
7. D1 sync payload matches Workers schema; campaigns marked synced stop resending (H5, Q2).
8. All script files <200 lines; `init_campaigns_db.py` removed (M4).
9. End-to-end verified on real Google Ads test account + live Cloudflare Workers.

## Unresolved Questions (to confirm before/at phase start)

- **Q1 RESOLVED**: Skill is headless (cron + Telegram). Phase 03 designs async gate.
- **Q2 RESOLVED**: Workers `/api/sync` exists but expects `{metrics,leads,campaigns,ad_groups,ads,keywords}` — current Hermes `{anomalies}` field is **ignored**. Phase 06 reconciles.
- **Q3 RECOMMENDED**: Budget = env const `MONTHLY_BUDGET=500` (not `SUM(monthly_budget)`). Phase 02 confirms env value as guardrail source.

## Out of Scope

- L2 (RSA key get_type), L4 (synthetic campaign_id) — defer to post-stabilization.
- Facebook/Meta, Smart Bidding, multi-user dashboard (per parent plan).
