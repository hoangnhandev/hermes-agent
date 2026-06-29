---
title: "Hermes Ads Copilot — Google Ads Lead Gen + Cloudflare Dashboard"
description: "Tier 1 Copilot system: Hermes Agent (3 skills) → Google Ads API → D1 Database → Workers API → Pages Dashboard. Human-in-the-loop for campaign creation, automated monitoring and reporting."
status: pending
priority: P2
effort: ~35h
branch: main
approach: tier1-copilot-cloudflare-d1
execution: copilot-with-human-approval
tags: [google-ads, lead-gen, cloudflare, d1, dashboard, hermes-skill, automation, copilot]
created: 2026-06-29
---

# Hermes Ads Copilot — Implementation Plan

## Overview

AI-powered Google Ads copilot for lead generation campaigns ($500/month budget).
Three Hermes skills (research → creator → monitor) push performance data to
Cloudflare D1 via Workers API, visualized on a Pages dashboard with 4 tabs.

Tier 1 architecture: **human-in-the-loop** for all campaign creation and budget
changes. AI handles research, copy generation, monitoring, and optimization
suggestions.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  HERMES AGENT (withly-server VPS)                        │
│                                                          │
│  Skill 1: google-ads-research    Skill 2: google-ads-    │
│  ┌──────────────────────────┐    creator                  │
│  │ Web search + LLM         │    ┌───────────────────┐  │
│  │ → keywords, audience,    │    │ LLM generates     │  │
│  │   competitor analysis     │    │ ad copy → human   │  │
│  │ → structured plan         │    │ approves → deploy │  │
│  └──────────────────────────┘    │ via Google Ads API│  │
│                                  └────────┬──────────┘  │
│  Skill 3: google-ads-monitor                      │       │
│  ┌──────────────────────────┐                       │       │
│  │ Cron (6h): query API     │                       │       │
│  │ → local SQLite backup    │                       │       │
│  │ → POST sync to D1       │◄──────────────────────┘       │
│  │ → LLM analyze → alert   │                               │
│  │ → Telegram daily report   │                               │
│  └───────────┬──────────────┘                               │
└──────────────┼──────────────────────────────────────────────┘
               │ HTTPS POST /api/sync
┌──────────────┼──────────────────────────────────────────────┐
│  CLOUDFLARE  ▼                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Workers API (JWT auth + API key for sync)          │  │
│  │  /api/metrics  /api/leads  /api/budget  /api/keywords│  │
│  └──────────────────────┬───────────────────────────────┘  │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Cloudflare D1 (ads_copilot DB)                      │  │
│  │  campaigns, ad_groups, ads, keywords,                │  │
│  │  daily_metrics, leads, ad_copy_history,               │  │
│  │  optimization_log                                      │  │
│  └──────────────────────┬───────────────────────────────┘  │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Cloudflare Pages (Dashboard)                         │  │
│  │  Tab 1: Campaign Overview | Tab 2: Lead Metrics      │  │
│  │  Tab 3: Ad Copy & Keywords | Tab 4: Budget Tracking  │  │
│  │  Chart.js (CDN) | 15min polling | JWT auth            │  │
│  └──────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

## Global Constraints

- **Tier 1 Copilot**: Human MUST approve all campaign creation, ad copy, and budget changes before API deployment. No auto-action on spend.
- **Budget guardrails**: Max daily budget = `monthly_budget / 30 * 2`. Hardcoded. Cannot be overridden by LLM.
- **Local-first storage**: Hermes VPS SQLite is source of truth. D1 is sync replica. Sync failures → alert human.
- **Policy compliance screening**: LLM-generated ad copy passes self-check against Google Ads policy list BEFORE entering approval queue.
- **Follow polymarket-signals conventions**: kebab-case dirs, snake_case files, underscore prefix for utilities, SKILL.md with YAML frontmatter, stdlib-first where possible.
- **Cloudflare account**: `1a9e25e3294f6410a8d5334f707466c9` (same as polymarket dashboard).
- **Google Ads**: New account, Search campaign type, Manual CPC initially (Smart Bidding needs 30+ conversions first).

## Phases

| # | Phase | Effort | Depends | File |
|---|-------|--------|---------|------|
| 00 | Google Ads account setup + API access (guided manual) | 2-4h | — | [phase-00](phase-00-account-and-api-setup.md) |
| 01 | Hermes skill: google-ads-research (LLM + web search) | 4-5h | — | [phase-01-skill-research.md) |
| 02 | Cloudflare D1 schema + Workers API + JWT auth | 6-8h | — | [phase-02-cloudflare-infra.md) |
| 03 | Hermes skill: google-ads-creator (Python + Google Ads API) | 6-8h | 00 | [phase-03-skill-creator.md) |
| 04 | Hermes skill: google-ads-monitor (cron + sync + alerts) | 5-6h | 02, 03 | [phase-04-skill-monitor.md) |
| 05 | Cloudflare Pages dashboard (4 tabs, Chart.js) | 6-8h | 02 | [phase-05-dashboard.md) |
| 06 | Integration testing + documentation | 2-3h | 04, 05 | [phase-06-integration-testing.md) |

## Success Criteria

1. Google Ads account created with conversion tracking operational
2. Hermes research skill generates keyword/audience plans validated by human
3. Hermes creator skill deploys approved campaigns via API (no errors)
4. Hermes monitor syncs metrics to D1 every 6h with no silent failures
5. Dashboard displays all 4 tabs with real data from D1
6. Daily Telegram report delivers KPIs automatically
7. Budget never exceeds 2x daily average in any 24h period
8. All ad copy passes policy screening before approval

## 🔴 3 Critical Risks (from /ck:scenario) — mitigated across phases

| # | Critical | Mitigation | Phase |
|---|----------|-----------|-------|
| C1 | Budget hallucination ($500/day vs /month) | Hardcoded `max_daily = monthly/30*2`. Human approval safety net. | 03, 04 |
| C2 | D1 sync silent failure → data loss | Local SQLite source of truth. D1 = replica. Alert after 3 consecutive failures. | 04 |
| C3 | Policy violation → account suspension | LLM self-screen copy against Google restricted terms list. Human review as final gate. | 03 |

## 🔶 12 High Risks — key mitigations

| # | Risk | Mitigation | Phase |
|---|------|-----------|-------|
| H1 | Google Ads API rate limit | Batch requests in groups of 10. Exponential backoff on 429. | 03, 04 |
| H2 | Cron race condition (overlap syncs) | SQLite WAL + UNIQUE constraints. Idempotent upsert. | 04 |
| H3 | D1 storage > 500MB free tier | Archive rows >90 days. Alert at 400MB. | 02, 04 |
| H4 | Dashboard auth bypass | JWT httpOnly cookie, 24h expiry, revocation table. | 02 |
| H5 | Sync API called by non-Hermes client | `X-Hermes-Secret` header. Rate limit 1 req/min. | 02 |
| H6 | JWT token stolen | httpOnly cookie, not localStorage. Revocation support. | 02 |
| H7 | Campaign deleted externally → orphan D1 data | Mark `archived`, not delete. Historical metrics preserved. | 04 |
| H8 | Duplicate leads (double conversion tracking) | UNIQUE(source, campaign_id, conversion_id). | 04 |
| H9 | Google Ads API version upgrade breaks scripts | Pin google-ads-python version. Test on test account first. | 03 |
| H10 | Daily spend accelerates (3x average) | Hermes detects pacing anomaly → alert human. No auto-action. | 04 |
| H11 | Lead form broken (0 conversions, normal clicks) | Hermes detects CPA spike → "Possible tracking issue" alert. | 04 |
| H12 | Campaign paused mid-sync → partial data | Atomic sync per entity. Next cron reconciles. | 04 |

## Dependencies

- Google Ads account (new, created in Phase 0)
- Google Cloud project with OAuth credentials (Phase 0)
- `google-ads-python` library (Phase 3)
- Cloudflare account with D1, Workers, Pages (existing account)
- Hermes Agent on withly-server VPS (existing)
- Hermes cron + Telegram gateway (existing)

## Out of Scope (locked)

- Facebook/Meta Ads integration (future plan after Google Ads stable)
- Full autopilot (Tier 3) — always human-in-the-loop
- Smart Bidding strategies (requires 30+ conversions first)
- E-commerce / sales tracking (lead gen only)
- Real-time dashboard (polling 15min sufficient)
- Multi-user dashboard (single owner)
- CRM integration (future)

## Effort Summary

| Category | Hours |
|----------|-------|
| Account setup (guided) | 2-4 |
| Hermes skills (3 skills) | 15-19 |
| Cloudflare infra (D1 + Workers + Pages) | 12-16 |
| Integration + testing | 2-3 |
| **Total** | **~35h** |
