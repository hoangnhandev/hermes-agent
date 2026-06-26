# Environment Variables (all OPTIONAL unless noted)

## API Keys (MVP requires none — all Polymarket endpoints are public/read-only)

| Variable | Required | Source | Notes |
|----------|----------|--------|-------|
| (none for MVP) | No | — | All Polymarket data is public/read-only |

## Deferred (Phase 03-04)

| Variable | Required | Source | Notes |
|----------|----------|--------|-------|
| `MANIFOLD_API_KEY` | No | manifold.markets | Free, optional; raises rate limit |
| `METACULUS_API_KEY` | No | metaculus.com | Free, optional; raises rate limit |
| `COINGECKO_API_KEY` | No | coingecko.com | Free tier; optional demo key |
| `TELEGRAM_CHAT_ID` | No | Hermes config | For gateway wiring; usually in hermes config |

## Important

**NO Polymarket trading key is ever needed.** This skill is signal-only —
no private keys, no EIP-712 signing, no order placement.
