# Phase 02 — Cloudflare D1 Schema + Workers API + JWT Auth

## Context
- Parent: [plan.md](plan.md). Depends: none (independent infra).
- Scenario criticals: H3 (D1 storage limit), H4 (auth bypass), H5 (sync API abuse), H6 (JWT theft).
- Blocks: Phase 04 (monitor needs sync endpoint), Phase 05 (dashboard needs metrics endpoints).

## Overview
Create the Cloudflare infrastructure layer: D1 database with full SQL schema,
Workers API with 7 endpoints (sync, metrics, leads, budget, keywords, auth login/refresh),
JWT authentication middleware, and wrangler deployment config. This is the data
persistence and API backbone for the entire copilot system.

## Key Insights
- **D1 = sync replica**: Hermes VPS SQLite is source of truth. D1 stores copies for
  dashboard queries. If D1 goes down, Hermes keeps running and sync catches up.
- **Two auth mechanisms**: (1) `X-Hermes-Secret` header for sync API (machine-to-machine),
  (2) JWT httpOnly cookie for dashboard API (human access). Never mix them.
- **Idempotent upsert**: sync API uses `INSERT OR REPLACE` with UNIQUE constraints.
  Same data sent twice = no duplicates. Critical for retry resilience.
- **D1 free tier = 5GB storage, 5M rows/day reads, 100K rows/day writes**.
  For $500/mo campaign, daily metrics = ~30 rows/day. Way under limits.

## Requirements
- **Functional**: D1 database created with full schema, 7 API endpoints, JWT auth, sync protocol.
- **Non-functional**: rate limit on sync (1 req/min), idempotent operations, <10ms P95 for D1 queries,
  Workers deployed via wrangler, environment vars in wrangler.toml secrets.

## Architecture
```
ads-copilot/
├── wrangler.toml              # Workers config + D1 binding
├── schema.sql                 # D1 schema (all tables + indexes)
├── src/
│   ├── index.ts               # Worker entry: route dispatch
│   ├── auth.ts                # JWT middleware + login/refresh
│   ├── sync-handler.ts        # POST /api/sync
│   ├── metrics-handler.ts     # GET /api/metrics
│   ├── leads-handler.ts       # GET /api/leads
│   ├── budget-handler.ts      # GET /api/budget
│   └── keywords-handler.ts    # GET /api/keywords
└── package.json               # wrangler, typescript deps
```

## Related Code Files
- **Create**: `plans/260629-1125-hermes-ads-copilot/infra/wrangler.toml`
- **Create**: `plans/260629-1125-hermes-ads-copilot/infra/schema.sql`
- **Create**: `plans/260629-1125-hermes-ads-copilot/infra/src/*.ts` (7 files)
- **Create**: `plans/260629-1125-hermes-ads-copilot/infra/package.json`
- **Deploy to**: Cloudflare Workers (account `1a9e25e3294f6410a8d5334f707466c9`)

## Interfaces

### Consumes
- **POST /api/sync**: `{ "secret": str, "metrics": [...], "leads": [...], "campaigns": [...], "keywords": [...] }`
  Auth: `X-Hermes-Secret` header.
- **POST /api/auth/login**: `{ "password": str }` → `{ "token": str }` (set as httpOnly cookie)
- **POST /api/auth/refresh**: Cookie auto-read → refreshed token

### Produces
- **GET /api/metrics** (JWT): `{ "campaigns": [...], "kpis": {...}, "trend": [...] }`
- **GET /api/leads** (JWT): `{ "leads": [...], "summary": {...}, "trend": [...] }`
- **GET /api/budget** (JWT): `{ "budget": {...}, "pacing": {...}, "forecast": {...} }`
- **GET /api/keywords** (JWT): `{ "keywords": [...], "ad_copy": [...], "suggestions": [...] }`

## Implementation Steps

### Step 1: D1 Database + Schema (1.5h)

Create via wrangler:
```bash
npx wrangler d1 create ads-copilot
# Note the database_id from output
```

Schema (`schema.sql`):
```sql
-- Campaigns (mirrors Google Ads structure)
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- active, paused, archived
    campaign_type TEXT NOT NULL DEFAULT 'search',  -- search, display, pmax, video
    objective TEXT NOT NULL DEFAULT 'lead_gen',  -- lead_gen, awareness, sales, traffic
    monthly_budget REAL NOT NULL,  -- per-campaign monthly budget
    daily_budget REAL NOT NULL,     -- per-campaign daily cap
    bid_strategy TEXT NOT NULL DEFAULT 'manual_cpc',
    has_conversion_tracking INTEGER NOT NULL DEFAULT 1,  -- 0=no, 1=yes
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Ad Groups
CREATE TABLE IF NOT EXISTS ad_groups (
    ad_group_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

-- Ads (ad copy)
CREATE TABLE IF NOT EXISTS ads (
    ad_id TEXT PRIMARY KEY,
    ad_group_id TEXT NOT NULL,
    headline_1 TEXT,
    headline_2 TEXT,
    headline_3 TEXT,
    description_1 TEXT,
    description_2 TEXT,
    final_url TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (ad_group_id) REFERENCES ad_groups(ad_group_id)
);

-- Keywords
CREATE TABLE IF NOT EXISTS keywords (
    keyword_id TEXT PRIMARY KEY,
    ad_group_id TEXT NOT NULL,
    keyword_text TEXT NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'PHRASE',  -- EXACT, PHRASE, BROAD
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (ad_group_id) REFERENCES ad_groups(ad_group_id)
);

-- Daily Metrics (time-series — core table for dashboard)
CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,  -- campaign, ad_group, ad, keyword
    entity_id TEXT NOT NULL,
    date TEXT NOT NULL,         -- YYYY-MM-DD
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0.0,
    conversions INTEGER NOT NULL DEFAULT 0,
    conversion_value REAL NOT NULL DEFAULT 0.0,
    UNIQUE(entity_type, entity_id, date)
);

-- Leads (from conversion tracking)
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,        -- google_ads, manual
    campaign_id TEXT,
    ad_group_id TEXT,
    ad_id TEXT,
    keyword_id TEXT,
    conversion_id TEXT,         -- Google's conversion ID
    conversion_date TEXT NOT NULL,
    conversion_data TEXT,        -- JSON: name, email, phone, message
    quality_score REAL DEFAULT 0.0,  -- 0-10 scale, manual or LLM-assigned
    status TEXT NOT NULL DEFAULT 'new',  -- new, contacted, qualified, lost
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, conversion_id)
);

-- Ad Copy History (LLM-generated, tracks approval + performance)
CREATE TABLE IF NOT EXISTS ad_copy_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    ad_group_id TEXT,
    headline_1 TEXT,
    headline_2 TEXT,
    headline_3 TEXT,
    description_1 TEXT,
    description_2 TEXT,
    approved INTEGER NOT NULL DEFAULT 0,  -- 0=pending, 1=approved, 2=rejected
    rejection_reason TEXT,
    performance_impressions INTEGER DEFAULT 0,
    performance_clicks INTEGER DEFAULT 0,
    performance_conversions INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

-- Optimization Log (LLM suggestions + outcomes)
CREATE TABLE IF NOT EXISTS optimization_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    suggestion TEXT NOT NULL,
    action_taken TEXT,           -- accepted, rejected, auto_applied, pending
    result TEXT,                 -- outcome after action
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Sync Status (track sync health)
CREATE TABLE IF NOT EXISTS sync_status (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- singleton row
    last_sync_at TEXT,
    last_sync_status TEXT NOT NULL DEFAULT 'never',  -- success, failed, never
    last_error TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    total_syncs INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Revoked Tokens (JWT revocation)
CREATE TABLE IF NOT EXISTS revoked_tokens (
    token_jti TEXT PRIMARY KEY,
    revoked_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);
```

Indexes for common dashboard queries:
```sql
CREATE INDEX IF NOT EXISTS idx_metrics_entity_date ON daily_metrics(entity_type, entity_id, date);
CREATE INDEX IF NOT EXISTS idx_metrics_date ON daily_metrics(date);
CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id);
CREATE INDEX IF NOT EXISTS idx_leads_date ON leads(conversion_date);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_copy_campaign ON ad_copy_history(campaign_id);
CREATE INDEX IF NOT EXISTS idx_copy_approved ON ad_copy_history(approved);
CREATE INDEX IF NOT EXISTS idx_opt_campaign ON optimization_log(campaign_id);
CREATE INDEX IF NOT EXISTS idx_opt_date ON optimization_log(created_at);
```

Apply schema:
```bash
npx wrangler d1 execute ads-copilot --remote --file=schema.sql
```

### Step 2: Workers API — Route Dispatch (1h)

`src/index.ts`:
```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    // Routes
    if (path === '/api/sync' && request.method === 'POST') return syncHandler(request, env);
    if (path === '/api/metrics' && request.method === 'GET') return metricsHandler(request, env);
    if (path === '/api/leads' && request.method === 'GET') return leadsHandler(request, env);
    if (path === '/api/budget' && request.method === 'GET') return budgetHandler(request, env);
    if (path === '/api/keywords' && request.method === 'GET') return keywordsHandler(request, env);
    if (path === '/api/auth/login' && request.method === 'POST') return loginHandler(request, env);
    if (path === '/api/auth/refresh' && request.method === 'POST') return refreshHandler(request, env);

    return new Response('Not Found', { status: 404 });
  },
};
```

### Step 3: JWT Auth Middleware (1.5h)

`src/auth.ts`:
```typescript
interface Env {
  DB: D1Database;
  JWT_SECRET: string;
  HERMES_SYNC_SECRET: string;
  DASHBOARD_PASSWORD: string;  // bcrypt hash
}

// JWT creation (login)
async function createJWT(payload: JWTPayload, secret: string, expiry: string = '24h'): Promise<string> {
  // Use Web Crypto API for HMAC-SHA256
  const header = { alg: 'HS256', typ: 'JWT' };
  const now = Math.floor(Date.now() / 1000);
  const exp = expiry === '24h' ? now + 86400 : now + 3600;
  const jti = crypto.randomUUID();

  const payloadWithMeta = { ...payload, jti, iat: now, exp };
  const encoded = base64url(JSON.stringify(header)) + '.' + base64url(JSON.stringify(payloadWithMeta));

  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(encoded));
  return encoded + '.' + base64url(new Uint8Array(signature));
}

// JWT verification middleware
async function verifyJWT(request: Request, env: Env): Promise<JWTPayload | null> {
  const cookie = getCookie(request, 'auth_token');
  if (!cookie) return null;

  const [header, payload, signature] = cookie.split('.');
  // Verify signature with HMAC-SHA256
  // Check expiry
  // Check revocation: SELECT 1 FROM revoked_tokens WHERE token_jti = ?
  // Return payload if valid, null if revoked or expired
}

// Sync API auth (machine-to-machine)
function verifySyncSecret(request: Request, env: Env): boolean {
  const secret = request.headers.get('X-Hermes-Secret');
  return secret === env.HERMES_SYNC_SECRET;
}
```

Rate limiter for sync (in-memory, per-Worker):
```typescript
const syncLimiter = { lastCall: 0, MIN_INTERVAL: 60000 }; // 1 min

function checkSyncRateLimit(): boolean {
  const now = Date.now();
  if (now - syncLimiter.lastCall < syncLimiter.MIN_INTERVAL) return false;
  syncLimiter.lastCall = now;
  return true;
}
```

### Step 4: Sync Handler (1h)

`src/sync-handler.ts`:
```typescript
async function syncHandler(request: Request, env: Env): Promise<Response> {
  // 1. Verify X-Hermes-Secret header
  if (!verifySyncSecret(request, env)) return unauthorized();

  // 2. Rate limit check
  if (!checkSyncRateLimit()) return rateLimited();

  // 3. Parse body
  const body = await request.json();
  // body.metrics: [{ entity_type, entity_id, date, impressions, clicks, cost, conversions }]
  // body.leads: [{ source, campaign_id, conversion_id, conversion_date, conversion_data }]
  // body.campaigns: [{ campaign_id, name, status, daily_budget }]
  // body.keywords: [{ keyword_id, ad_group_id, keyword_text, match_type }]

  // 4. Upsert campaigns (INSERT OR REPLACE)
  // 5. Upsert ad_groups, ads, keywords
  // 6. Upsert daily_metrics (UNIQUE constraint prevents duplicates)
  // 7. Upsert leads (UNIQUE source+conversion_id)
  // 8. Update sync_status: last_sync_at=now, status=success, failures=0
  // 9. On error: update sync_status: status=failed, increment failures

  // All wrapped in a single D1 batch for atomicity
  const statements = buildUpsertStatements(body);
  await env.DB.batch(statements);

  return success({ synced_at: new Date().toISOString() });
}
```

### Step 5: Metrics + Leads + Budget + Keywords Handlers (2h)

Each follows same pattern: verify JWT → build query → return JSON.

**GET /api/metrics**:
```sql
-- MULTI-CAMPAIGN: per-campaign KPIs (primary view), account total (secondary)
-- Campaigns grouped individually, not rolled into aggregate avg CPC

-- Per-campaign KPIs (30 days)
SELECT c.campaign_id, c.name, c.objective, c.status,
  SUM(m.impressions) as impressions, SUM(m.clicks) as clicks,
  SUM(m.cost) as cost, SUM(m.conversions) as conversions,
  ROUND(SUM(m.clicks) * 100.0 / NULLIF(SUM(m.impressions), 0), 2) as ctr,
  ROUND(SUM(m.cost) / NULLIF(SUM(m.clicks), 0), 2) as cpc,
  ROUND(SUM(m.cost) / NULLIF(SUM(m.conversions), 0), 2) as cpl
FROM campaigns c JOIN daily_metrics m ON c.campaign_id = m.entity_id
WHERE m.entity_type = 'campaign' AND m.date >= date('now', '-30 days')
  AND c.status != 'archived'
GROUP BY c.campaign_id ORDER BY cost DESC;

-- Account totals (computed in TS from above, NOT via AVG in SQL)
-- total_impressions = sum, total_clicks = sum, total_cost = sum
-- total_conversions = sum
-- account_ctr = total_clicks / total_impressions * 100
-- account_cpc = total_cost / total_clicks  (NOT avg of per-campaign CPCs)

-- 30-day trend (per-campaign, stacked or multi-line)
SELECT m.entity_id as campaign_id, c.name, m.date,
  SUM(m.impressions) as impressions, SUM(m.clicks) as clicks,
  SUM(m.cost) as cost, SUM(m.conversions) as conversions
FROM campaigns c JOIN daily_metrics m ON c.campaign_id = m.entity_id
WHERE m.entity_type = 'campaign' AND m.date >= date('now', '-30 days')
  AND c.status != 'archived'
GROUP BY m.entity_id, m.date ORDER BY m.entity_id, m.date;
```

**GET /api/leads**:
```sql
-- MULTI-CAMPAIGN: leads per campaign + per-campaign quality
-- Campaigns without conversion tracking (awareness) won't appear here — expected

-- Leads today + this week + all time (per campaign)
SELECT c.campaign_id, c.name, c.objective,
  COUNT(CASE WHEN l.conversion_date = date('now') THEN 1 END) as leads_today,
  COUNT(CASE WHEN l.conversion_date >= date('now', '-7 days') THEN 1 END) as leads_week,
  COUNT(*) as leads_total,
  ROUND(AVG(l.quality_score), 1) as avg_quality
FROM campaigns c LEFT JOIN leads l ON c.campaign_id = l.campaign_id
WHERE c.status != 'archived' AND c.has_conversion_tracking = 1
GROUP BY c.campaign_id ORDER BY leads_week DESC;

-- Lead trend (last 30 days, per campaign)
SELECT c.campaign_id, c.name,
  l.conversion_date as date, COUNT(*) as leads
FROM campaigns c JOIN leads l ON c.campaign_id = l.campaign_id
WHERE l.conversion_date >= date('now', '-30 days')
  AND c.status != 'archived' AND c.has_conversion_tracking = 1
GROUP BY c.campaign_id, l.conversion_date ORDER BY c.campaign_id, l.conversion_date;
```

**GET /api/budget**:
```sql
-- MULTI-CAMPAIGN: per-campaign pacing + budget guardrails
-- Pacing done per-campaign, not account aggregate
-- Campaigns without conversion tracking (has_conversion_tracking=0) skip CPA/conv metrics

-- Budget progress (current month, per-campaign)
SELECT c.campaign_id, c.name, c.objective, c.monthly_budget, c.daily_budget,
  c.has_conversion_tracking,
  SUM(m.cost) as spend_this_month
FROM campaigns c JOIN daily_metrics m ON c.campaign_id = m.entity_id
WHERE m.entity_type = 'campaign' AND m.date >= date('now', 'start of month')
  AND c.status = 'active'
GROUP BY c.campaign_id;

-- Per-campaign pacing calculation (TypeScript):
// For EACH active campaign:
//   daily_budget_cap = campaign.daily_budget * 2  ← per-campaign guardrail
//   days_elapsed = day_of_month
//   days_remaining = 30 - days_elapsed
//   expected_spend_now = campaign.daily_budget * days_elapsed
//   pacing_pct = actual_spend / expected_spend_now * 100
//   forecast_end_of_month = actual_spend + (actual_spend / days_elapsed * days_remaining)
//   pacing_status = 'over' if pacing_pct > 110, 'under' if < 90, else 'on_track'
//
// Account-level totals computed in TypeScript after per-campaign rows:
//   total_spend = sum of all campaign spends
//   total_budget = sum of all campaign monthly_budgets
//   total_pacing = total_spend / (total_budget / 30 * days_elapsed) * 100
```

**GET /api/keywords**:
```sql
-- Top keywords by conversions
SELECT k.keyword_text, k.match_type,
  SUM(m.impressions) as impressions, SUM(m.clicks) as clicks,
  ROUND(SUM(m.cost) / NULLIF(SUM(m.clicks), 0), 2) as cpc,
  SUM(m.conversions) as conversions
FROM keywords k JOIN daily_metrics m ON k.keyword_id = m.entity_id
WHERE m.entity_type = 'keyword' AND m.date >= date('now', '-30 days')
GROUP BY k.keyword_id ORDER BY conversions DESC LIMIT 50;

-- Ad copy performance
SELECT a.headline_1, a.headline_2, a.description_1,
  SUM(m.impressions), SUM(m.clicks), SUM(m.conversions)
FROM ads a JOIN daily_metrics m ON a.ad_id = m.entity_id
WHERE m.entity_type = 'ad' AND m.date >= date('now', '-30 days')
GROUP BY a.ad_id ORDER BY m.conversions DESC;
```

### Step 6: Wrangler Config (30 min)

`wrangler.toml`:
```toml
name = "ads-copilot-api"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[[d1_databases]]
binding = "DB"
database_name = "ads-copilot"
database_id = "PASTE_FROM_CREATE_COMMAND"

[vars]
ENVIRONMENT = "production"

# Secrets (set via CLI, NOT in toml):
# npx wrangler secret put JWT_SECRET
# npx wrangler secret put HERMES_SYNC_SECRET
# npx wrangler secret put DASHBOARD_PASSWORD
```

### Step 7: Deploy + Verify (30 min)
```bash
# Install deps
npm install wrangler typescript @cloudflare/workers-types

# Set secrets
npx wrangler secret put JWT_SECRET
npx wrangler secret put HERMES_SYNC_SECRET
npx wrangler secret put DASHBOARD_PASSWORD

# Deploy
npx wrangler deploy

# Verify
curl -X POST https://ads-copilot-api.<subdomain>.workers.dev/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password":"your_password"}' \
  -c cookies.txt

curl https://ads-copilot-api.<subdomain>.workers.dev/api/metrics \
  -b cookies.txt
# → {"campaigns":[],"kpis":{...},"trend":[]}  (empty, expected)
```

## Todo
- [ ] Create D1 database via wrangler
- [ ] Write schema.sql (9 tables + 8 indexes)
- [ ] Apply schema to D1 (remote)
- [ ] Create `src/index.ts` — route dispatch
- [ ] Create `src/auth.ts` — JWT create/verify/revoke + sync secret
- [ ] Create `src/sync-handler.ts` — POST /api/sync with batch upsert + rate limit
- [ ] Create `src/metrics-handler.ts` — GET /api/metrics (KPIs + trend + comparison)
- [ ] Create `src/leads-handler.ts` — GET /api/leads (summary + quality + trend)
- [ ] Create `src/budget-handler.ts` — GET /api/budget (pacing + forecast)
- [ ] Create `src/keywords-handler.ts` — GET /api/keywords (performance + ad copy)
- [ ] Write wrangler.toml with D1 binding
- [ ] Set secrets (JWT_SECRET, HERMES_SYNC_SECRET, DASHBOARD_PASSWORD)
- [ ] Deploy to Workers
- [ ] Verify: login → get JWT → query metrics endpoint

## Success Criteria
- D1 database created with 9 tables + indexes applied
- POST /api/sync with valid X-Hermes-Secret → 200 + upserts data
- POST /api/sync with wrong secret → 401
- POST /api/sync rate limited → 429 after <1min
- POST /api/auth/login with correct password → set-cookie with JWT
- GET /api/metrics with valid JWT → 200 + JSON
- GET /api/metrics without JWT → 401
- POST /api/auth/refresh with valid cookie → refreshed token
- All 7 endpoints respond correctly (verified with curl)

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| D1 batch size limit (H3) | Med | Batch in chunks of 100. Metrics per sync = ~30 rows. Never hit limit. |
| JWT secret leaks (H6) | High | Store as wrangler secret (never in toml or code). httpOnly cookie (not localStorage). |
| Sync API abuse (H5) | High | X-Hermes-Secret header + 1 req/min rate limit. Rotate secret quarterly. |
| Auth bypass (H4) | High | JWT signature verification on every request. Revocation table for immediate logout. |
| Workers cold start latency | Low | D1 queries <10ms. Cold start ~50ms. Dashboard polls every 15min — acceptable. |

## Security
- JWT: HMAC-SHA256 via Web Crypto API, httpOnly cookie, 24h expiry, jti-based revocation
- Sync API: shared secret header, rate limited, no JWT needed
- D1: no public access (Workers-only binding)
- Password: bcrypt hash stored as secret, never plaintext in code
- CORS: restrict origins to dashboard Pages URL only

## Next Steps
- Phase 04 (monitor) — uses POST /api/sync endpoint
- Phase 05 (dashboard) — uses GET /api/metrics, /api/leads, /api/budget, /api/keywords
