---
title: "Polymarket LLM Signal Bot on Hermes Agent"
description: "Calibration-driven, signal-only Polymarket prediction system as a Hermes skill."
status: COMPLETE (MVP)
priority: P2
effort: ~15h  # <!-- RED-TEAM F-08 --> MVP (phases 00-02) only; was 32h
deferred_phases: [03, 04, 05]  # <!-- RED-TEAM F-08 --> separate future gated plan
branch: main
approach: calibration-loop
execution: signal-only
tags: [polymarket, prediction-markets, llm, calibration, hermes-skill]
created: 2026-06-26
---

# Polymarket LLM Signal Bot — Implementation Plan

## Overview

Turn the approved brainstorm (Approach B) into a Hermes **skill** at the edge:
`skills/research/polymarket-signals/`. Cron scans Crypto+Politics markets, an LLM
predicts P(event), crowd/data sources ensemble, every prediction is logged to
SQLite, and Telegram alerts fire **only** when a category is historically
calibrated and shows realized edge. Signal-only — no key, no order, no signing.

Design source of truth: `plans/20260626-polymarket-signal-bot-brainstorm.md`.

> **MVP = phases 00-02 (~15h). Phases 03-05 deferred to a separate plan, gated on phase-02 producing directional calibration signal (per Red Team F-08).** <!-- RED-TEAM F-08 -->

## Global Constraints

- **Approach**: B — calibration-driven signal system (predict → track → gate).
- **Execution**: signal-only. NO private key, NO EIP-712 signing, NO order placement anywhere.
- **Markets**: Crypto + Politics only.
- **Sources**: LLM + web search + crowd aggregates (Manifold/Metaculus) + specialized data (polling/CoinGecko/on-chain).
- **Skill home**: `skills/research/polymarket-signals/` (sibling of read-only `skills/research/polymarket/`).
- **Store**: SQLite at `~/.hermes/polymarket_signals.db` (profile-aware via `get_hermes_home()`).
- **Config/keys**: `${HERMES_HOME:-~/.hermes}/.env` (or `~/.hermes/hermes.env`) — secrets only.
- **Scheduling/alerting**: Hermes cron + Hermes gateway → Telegram. Never core edits.
- **Cron execution model (MUST PIN before phase-02 code)** <!-- RED-TEAM F-01 -->: Hermes cron has two modes — `no_agent=True` (script stdout verbatim, NO agent, NO tools) OR default (script runs to completion THEN agent gets one-shot context). There is NO per-market `web_search` loop driven by a script. Phase-02 MUST pin one of: (a) `predict.py` IS the LLM client (calls provider directly, fetches web context script-side, runs `no_agent=True`), OR (b) agent-driven prompt-loop where the agent iterates markets calling `terminal` helper scripts per market.
- **Prompt caching sacred**: market data is a user/tool message, never in the system prompt prefix.
- **Scripts**: stdlib-first (urllib/json/argparse), invoked via `terminal` tool, <200 lines each.
- **Naming**: kebab-case filenames; YAGNI/KISS/DRY.

## Key Dependencies

- Reuses read-only `skills/research/polymarket/` endpoint knowledge (no code dup — reference it).
- Hermes cron scheduler + Telegram gateway must be operational on `withly-server` (open Q).
- Calibration needs **weeks** of resolved markets — expectations set in every phase.

## Phases

| # | Phase | Status | Effort | Depends | File |
|---|---|---|---|---|---|
| 00 | Setup, scaffold, SQLite store | COMPLETE | 5h | — | [phase-00](phase-00-setup-scaffold-store.md) |
| 01 | Data clients (markets/prices/resolution) | COMPLETE | 5h | 00 | [phase-01](phase-01-data-clients.md) |
| 02 | LLM predictor MVP + cron scan + alert | COMPLETE | 7h | 01 | [phase-02](phase-02-llm-predictor-mvp.md) |
| 03 | Crowd aggregates (Manifold/Metaculus) | **deferred** <!-- RED-TEAM F-08 --> | 5h | 02 | [phase-03](phase-03-crowd-aggregates.md) |
| 04 | Specialized data + calibrated gating | **deferred** <!-- RED-TEAM F-08 --> | 6h | 03 | [phase-04](phase-04-specialized-data-and-calibrated-gating.md) |
| 05 | Evaluation report + go/no-go | **deferred** <!-- RED-TEAM F-08 --> | 4h | 04 | [phase-05](phase-05-evaluation.md) |

**MVP = phases 00-02 (~15h).** Phases 03-05 are **DEFERRED** out of MVP (Red Team F-08) to a separate future plan, gated on phase-02 producing a directional calibration signal. Phase 02's terminal deliverable is a **re-evaluation checkpoint**: after 4-6 weeks of resolved history, run a one-off Brier calculation and decide whether ensemble/gating (phases 03-05) earns its effort before building them. <!-- RED-TEAM F-08 -->

## Success Criteria (overall)

- Skill loads and runs via `terminal` + Hermes cron with zero core edits.
- Every prediction logged with predicted_p, market_p, sources, category, confidence.
- Brier score + calibration curve computable per category from resolved history.
- Alerts carry an explicit calibration flag; no alert fires pre-evidence.
- Phase 05 delivers a documented go/no-go for any future automation.

## Out of Scope (locked)

Auto-execute, key trading, EIP-712 signing, real-money automation, model fine-tuning, deterministic arbitrage as core.

## Red Team Review

### Session — 2026-06-26
**Findings:** 15 (12 accepted incl. scope cut; 3 moot-by-defer)
**Severity breakdown:** 8 Critical, 7 High

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| F-01 | Cron execution model unverifiably wrong | Critical | Accept | P00/P02 |
| F-02 | CLOB V2 cutover broke reused V1 endpoints | Critical | Accept | P01 |
| F-03 | No idempotency → duplicate predictions | Critical | Accept | P00/P02 |
| F-04 | Predictions logged after LLM call → silent loss | Critical | Accept | P02 |
| F-05 | SQLite concurrency in shared cron env | Critical | Accept | P00 |
| F-06 | resolution misparse / UMA disputes corrupt calibration | Critical | Accept | P00/P01/P04 |
| F-07 | Prompt injection via untrusted content | Critical | Accept | P02 |
| F-08 | Scope over-built; phases 03-05 premature | Critical | Accept (MVP cut) | plan.md |
| F-09 | Silent cron failure, no user notification | High | Accept | P02 |
| F-10 | Category mis-tagging corrupts buckets | High | Accept | P00/P01 |
| F-11 | Cost runaway, no budget, prompt-cache misapplied | High | Accept | P01/P02 |
| F-12 | Store no migration/backup/recovery | High | Accept | P00 |
| F-13 | Cross-platform matching wrong + P03 gold-plate | High | Moot (deferred) | P03* |
| F-14 | Calibration never reaches significance | High | Moot (deferred) | P04* |
| F-15 | No free politics-polling API | High | Moot (deferred) | P04* |

\* P03-P05 deferred out of MVP per F-08.

**Key blockers to verify before any code (F-01, F-02):** (1) which Hermes cron execution model the predictor uses; (2) CLOB V2 endpoint shape post 2026-04-28 cutover.
