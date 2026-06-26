# API Endpoints Reference (verified live 2026-06-26)

## Base URLs

| API | Base URL | Rate Limit |
|-----|----------|------------|
| Gamma (discovery) | `https://gamma-api.polymarket.com` | 4,000 / 10s |
| CLOB (prices) | `https://clob.polymarket.com` | 9,000 / 10s |
| Data (trades) | `https://data-api.polymarket.com` | 1,000 / 10s |

## Category Filtering (Phase 01)

Uses `/events` endpoint with `tag_slug` parameter (NOT `/markets` with `tag_id`).

```bash
# Crypto markets
curl -s "https://gamma-api.polymarket.com/events?tag_slug=crypto&active=true&closed=false&order=volume&ascending=false&limit=10"

# Politics markets
curl -s "https://gamma-api.polymarket.com/events?tag_slug=politics&active=true&closed=false&order=volume&ascending=false&limit=10"

# Elections
curl -s "https://gamma-api.polymarket.com/events?tag_slug=elections&active=true&closed=false&order=volume&ascending=false&limit=10"
```

Known tag slugs: `crypto`, `bitcoin`, `politics`, `elections`, `us-presidential-election`,
`sports`, `science`, `world-elections`.

## CLOB Price Endpoints (V1, verified working)

```bash
# Midpoint price
curl -s "https://clob.polymarket.com/midpoint?token_id=TOKEN_ID"
# → {"mid": "0.77"}

# Spread
curl -s "https://clob.polymarket.com/spread?token_id=TOKEN_ID"
# → {"spread": "0.02"}

# Best price (buy)
curl -s "https://clob.polymarket.com/price?token_id=TOKEN_ID&side=buy"
# → {"price": "0.76"}

# Full orderbook
curl -s "https://clob.polymarket.com/book?token_id=TOKEN_ID"
```

## Price History (V2 — startTs+endTs required)

```bash
# Last 7 days of price history (startTs and endTs in milliseconds)
# NOTE: max window ~7 days per request; longer intervals return 400
curl -s "https://clob.polymarket.com/prices-history?market=CONDITION_ID&startTs=START_MS&endTs=END_MS&fidelity=60"
# → {"history": [[t_ms, price], ...]}
```

**Important:** `interval=all` no longer works. Must use `startTs`+`endTs` or explicit interval
(`1h`, `1d`). Short intervals (< 1h) may return empty arrays for low-activity markets.

## Gamma Market Lookup

```bash
# Search markets
curl -s "https://gamma-api.polymarket.com/public-search?q=bitcoin"

# Closed markets (for resolution checking)
curl -s "https://gamma-api.polymarket.com/markets?closed=true&limit=10&order=endDate&ascending=false"
```

## Data API (trades)

```bash
# Recent trades
curl -s "https://data-api.polymarket.com/trades?limit=10&market=CONDITION_ID"

# Open interest
curl -s "https://data-api.polymarket.com/oi?market=CONDITION_ID"
```

## Double-Encoded Fields

Gamma returns these as JSON strings inside JSON — always `json.loads()` before use:
- `outcomePrices` → `["0.65", "0.35"]`
- `clobTokenIds` → `["token_yes_id", "token_no_id"]`
- `outcomes` → `["Yes", "No"]`

## Sibling Skill Reference

See `../polymarket/references/api-endpoints.md` for the original read-only reference.
