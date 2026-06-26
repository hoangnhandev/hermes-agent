---
name: polymarket-signals
description: "Calibrated Polymarket signal bot. Cron scans Crypto+Politics markets."
version: 0.1.0
author: Hermes Agent
tags: [polymarket, prediction-markets, llm, calibration, hermes-skill]
platforms: [linux, macos, windows]
---

# Polymarket Signals Skill

Calibration-driven prediction signal system for Polymarket Crypto+Politics
markets. Cron scans discover active markets, an LLM predicts P(event), and
every prediction is logged to SQLite for later calibration scoring.

**Signal-only** — no trading keys, no order placement, no EIP-712 signing.

> MVP = phases 00-02. Alerts are explicitly "uncalibrated — paper trade" until
> enough resolved history accumulates (4-6 weeks). Phases 03-05 (crowd
> ensemble, calibrated gating, evaluation) are deferred to a future plan.

## When to Use

- User wants to set up a Polymarket prediction signal bot
- User asks about market calibration, Brier scores, or prediction tracking
- User wants automated market scanning with Telegram alerts
- User asks to run a prediction scan or check calibration status

## Prerequisites

- Hermes gateway running with Telegram connected (for alert delivery)
- No API keys required for MVP (all Polymarket endpoints are public/read-only)
- Optional: `MANIFOLD_API_KEY`, `METACULUS_API_KEY` (deferred, phase 03)
- Optional: `COINGECKO_API_KEY` (deferred, phase 04)

## How to Run

### Database Setup (one-time)

```bash
python3 scripts/store.py init
```

### Market Scan

```bash
python3 scripts/markets_client.py scan --categories crypto,politics
```

### Prediction Scan (MVP)

The prediction scan uses the **agent-driven cron model** (mode B): the agent
iterates markets, performs `web_search` per market, and calls `terminal` helper
scripts. See `## Procedure` for the full workflow.

```bash
# Dry-run (no LLM, just logs market universe)
python3 scripts/predict.py run-scan --dry-run --max-markets 5
```

### Cron Setup

```bash
# Agent-driven prediction scan (every 12 hours)
hermes cron add "0 0,12 * * *" \
  --name "Polymarket Signal Scan" \
  --deliver telegram \
  --skill polymarket-signals \
  --workdir "$HERMES_HOME/skills/research/polymarket-signals"

# Pin to cheap model (prevent silent cost drift)
cron job action=update model=haiku

# Resolution check (daily, separate cron)
hermes cron add "0 3 * * *" \
  --name "Polymarket Resolution Check" \
  --deliver telegram \
  --skill polymarket-signals \
  --script "python3 scripts/resolution_client.py check" \
  --workdir "$HERMES_HOME/skills/research/polymarket-signals"
```

## Quick Reference

| Script | Purpose | Phase |
|--------|---------|-------|
| `store.py` | SQLite schema + CRUD | 00 |
| `_paths.py` | DB path helper | 00 |
| `_http.py` | Shared HTTP helpers | 01 |
| `markets_client.py` | Discover + filter markets | 01 |
| `prices_client.py` | Fetch live prices | 01 |
| `resolution_client.py` | Check resolved markets | 01 |
| `predict.py` | LLM prediction + alert | 02 |

## Procedure

### Phase 00-01: Data Collection (automated, no LLM)

1. `markets_client.py scan` discovers active Crypto+Politics markets via Gamma API
2. Markets filtered by min liquidity/volume, tagged by category (`tag_slug` on `/events`)
3. Each market upserted into SQLite `markets` table
4. `resolution_client.py check` fills outcomes for recently-resolved markets

### Phase 02: LLM Prediction (agent-driven, MVP)

The agent IS the LLM client. This script stays LLM-client-free. The agent handles:

1. Agent calls `terminal`: `python3 scripts/predict.py run-scan --max-markets 20`
   - Script creates scan_id, discovers markets, inserts pending predictions, outputs markets JSON
2. For each market in the output, agent performs these steps:
   a. `web_search` for context (verbose, time-bracketed snippets)
   b. Agent calls the LLM with the byte-stable system prompt + user msg containing:
      "Question: <wrapped in UNTRUSTED_nonce> + context: <wrapped> + market price: <p>"
   c. LLM returns JSON: `{"predicted_p": ..., "confidence": ..., "rationale": ...}`
   d. Agent calls: `python3 scripts/predict.py predict-one --condition-id CID --scan-id SID --market-p P --category C --llm-json '<json>'`
   - Script validates JSON, range-checks values, sanitizes rationale (prompt injection F-07)
3. After loop, agent calls: `python3 scripts/predict.py alerts --scan-id SID --edge-threshold 0.10`
   - Script outputs formatted Telegram alerts with "uncalibrated — paper trade" disclaimer
4. Agent's final message (the alerts) is delivered to Telegram via cron default mode

### Prompt Caching

The system prompt (`prompt_template.txt`) is byte-stable — NO market data.
Market data goes into user/tool messages only. This preserves the cache prefix.

## Pitfalls

- **Uncalibrated alerts**: Every Phase 02 alert carries a paper-trade disclaimer.
  Trust the calibration loop, not individual predictions.
- **Cost control**: `--max-markets ~20` caps per-scan LLM/web spend. Model pinned
  to cheap tier via `cron job action=update model=haiku`.
- **Category tagging**: Uses `tag_slug=` on `/events` endpoint (Gamma API),
  NOT `tag_id=` on `/markets`. Fallback: keyword derivation from slug/tags.
- **Price history**: CLOB `/prices-history` requires `startTs`+`endTs` (not
  `interval=all` as in old docs). Max window ~7 days per request.
- **Prompt injection**: All untrusted content (market questions, web snippets)
  is wrapped in randomized delimiters. Validate `predicted_p` range.

## Verification

1. `python3 scripts/store.py init` — creates DB without error
2. `python3 scripts/markets_client.py scan` — persists ≥1 market per category
3. `python3 scripts/predict.py run-scan --dry-run --max-markets 3` — logs 3 predictions
4. `python3 scripts/store.py stats` — shows prediction counts
5. Alerts contain `"uncalibrated — paper trade"` (verify in Telegram delivery)
