# Phase 05 — Cloudflare Pages Dashboard (4 Tabs)

## Context
- Parent: [plan.md](plan.md). Depends: Phase 02 (Workers API + D1 schema + JWT auth).
- Scenario criticals: H4 (auth bypass), H6 (JWT theft), mobile responsive, empty state handling.
- Blocks: Phase 06 (integration testing).

## Overview
Build a Cloudflare Pages dashboard for the Ads Copilot: 4 tabs (Campaign Overview,
Lead Metrics, Ad Copy & Keywords, Budget Tracking), dark theme, Chart.js via CDN,
JWT auth flow, 15min polling, mobile-responsive. Vanilla HTML/CSS/JS — no framework.

## Key Insights
- **Vanilla stack = zero build step**: single `index.html` with embedded CSS + JS.
  Deploy directly to Pages. No bundler, no npm, no framework overhead.
- **Chart.js pinned version**: CDN link with specific version (e.g. `4.4.7`).
  Never use `latest` — breaking changes on CDN updates would break dashboard.
- **Auth is page-level**: login page → POST /api/auth/login → set httpOnly cookie →
  redirect to dashboard. No SPA routing. Cookie checked on every page load + API call.
- **Empty state is the default state**: new users have 0 campaigns. Every tab must show
  friendly "No data yet" message instead of blank/empty charts. Critical UX.
- **15min polling is sufficient**: this is not a real-time trading dashboard.
  15min refresh keeps data fresh without hammering Workers API.

## Requirements
- **Functional**: 4 tabs with KPIs, charts, tables, empty states, auth flow, auto-refresh.
- **Non-functional**: vanilla HTML/CSS/JS, Chart.js CDN (pinned), dark theme, <50KB total
  page size (excluding Chart.js), mobile-responsive, accessible (contrast ratios).

## Architecture
```
ads-copilot-dashboard/
├── index.html           # login page (redirects if authed)
├── dashboard.html       # main dashboard with 4 tabs
├── login.js             # login form handler + cookie management
├── dashboard.js         # tab switching, API calls, chart rendering
├── charts.js            # Chart.js wrapper (all chart configs)
├── auth.js              # JWT cookie check, redirect to login if expired
└── style.css            # dark theme, responsive layout, tab styles
```

Data flow:
```
User opens dashboard URL
  → auth.js checks for auth_token cookie
  → No cookie → redirect to index.html (login page)
  → User enters password → POST /api/auth/login
  → Set httpOnly cookie → redirect to dashboard.html
  → dashboard.js loads all 4 tabs via parallel fetch():
      GET /api/metrics → Tab 1 (Campaign Overview)
      GET /api/leads → Tab 2 (Lead Metrics)
      GET /api/keywords → Tab 3 (Ad Copy & Keywords)
      GET /api/budget → Tab 4 (Budget Tracking)
  → Charts rendered via Chart.js
  → setInterval(15min) → re-fetch all tabs
```

## Related Code Files
- **Create**: `plans/260629-1125-hermes-ads-copilot/dashboard/index.html`
- **Create**: `plans/260629-1125-hermes-ads-copilot/dashboard/dashboard.html`
- **Create**: `plans/260629-1125-hermes-ads-copilot/dashboard/login.js`
- **Create**: `plans/260629-1125-hermes-ads-copilot/dashboard/dashboard.js`
- **Create**: `plans/260629-1125-hermes-ads-copilot/dashboard/charts.js`
- **Create**: `plans/260629-1125-hermes-ads-copilot/dashboard/auth.js`
- **Create**: `plans/260629-1125-hermes-ads-copilot/dashboard/style.css`
- **Read**: Phase 02 Workers API endpoints (all GET endpoints)

## Interfaces

### Consumes
- **GET /api/metrics** (JWT cookie): `{ campaigns, kpis, trend, top_keywords }`
- **GET /api/leads** (JWT cookie): `{ leads, summary, trend, source_breakdown }`
- **GET /api/budget** (JWT cookie): `{ budget, pacing, forecast }`
- **GET /api/keywords** (JWT cookie): `{ keywords, ad_copy, suggestions }`
- **POST /api/auth/login**: `{ password }` → httpOnly cookie
- **POST /api/auth/refresh**: cookie → refreshed token

### Produces
- Rendered HTML page with 4 tabs
- Chart.js visualizations (line, bar, doughnut charts)
- No data written — dashboard is read-only

## Implementation Steps

### Step 1: Dark Theme CSS (1h)

`style.css` core design tokens:
```css
:root {
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-tertiary: #21262d;
  --border: #30363d;
  --text-primary: #e6edf3;
  --text-secondary: #8b949e;
  --accent-blue: #58a6ff;
  --accent-green: #3fb950;
  --accent-red: #f85149;
  --accent-yellow: #d29922;
  --accent-purple: #bc8cff;
  --radius: 8px;
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
}

body {
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font);
  margin: 0;
  padding: 0;
  line-height: 1.5;
}

/* KPI cards */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.kpi-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}

.kpi-card .label { color: var(--text-secondary); font-size: 12px; text-transform: uppercase; }
.kpi-card .value { font-size: 28px; font-weight: 700; }
.kpi-card .change { font-size: 13px; }
.kpi-card .change.positive { color: var(--accent-green); }
.kpi-card .change.negative { color: var(--accent-red); }

/* Tab navigation */
.tab-nav {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0;
  margin-bottom: 24px;
}

.tab-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  padding: 12px 20px;
  cursor: pointer;
  font-size: 14px;
  border-bottom: 2px solid transparent;
}

.tab-btn.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent-blue);
}

.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* Charts container */
.chart-container {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 24px;
}

/* Tables */
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.data-table th {
  text-align: left;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.data-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

/* Budget progress bar */
.progress-bar {
  background: var(--bg-tertiary);
  border-radius: 4px;
  height: 24px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease;
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: 48px;
  color: var(--text-secondary);
}

.empty-state .icon { font-size: 48px; margin-bottom: 16px; }

/* Responsive */
@media (max-width: 768px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .tab-nav { overflow-x: auto; }
  .data-table { font-size: 12px; }
}

@media (max-width: 480px) {
  .kpi-grid { grid-template-columns: 1fr; }
}
```

### Step 2: Auth Flow (1h)

`auth.js`:
```javascript
// auth.js — Check JWT cookie, redirect if missing/expired

const AUTH_COOKIE = 'auth_token';
const DASHBOARD_URL = 'dashboard.html';
const LOGIN_URL = 'index.html';

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? match[2] : null;
}

function checkAuth() {
  const token = getCookie(AUTH_COOKIE);
  if (!token) {
    window.location.href = LOGIN_URL;
    return false;
  }
  // Decode JWT payload to check expiry (no verification needed — server does that)
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    if (payload.exp * 1000 < Date.now()) {
      // Token expired → try refresh
      refreshAndRedirect();
      return false;
    }
    return true;
  } catch {
    window.location.href = LOGIN_URL;
    return false;
  }
}

async function refreshAndRedirect() {
  try {
    const resp = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' });
    if (resp.ok) {
      window.location.href = DASHBOARD_URL;
    } else {
      window.location.href = LOGIN_URL;
    }
  } catch {
    window.location.href = LOGIN_URL;
  }
}
```

`index.html` (login page):
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ads Copilot — Login</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <div style="max-width:400px;margin:100px auto;padding:32px;background:var(--bg-secondary);border-radius:var(--radius);border:1px solid var(--border)">
    <h2 style="margin-top:0">Ads Copilot</h2>
    <form id="login-form">
      <input type="password" id="password" placeholder="Password" required
        style="width:100%;padding:12px;background:var(--bg-tertiary);border:1px solid var(--border);color:var(--text-primary);border-radius:4px;font-size:14px;box-sizing:border-box">
      <p id="error" style="color:var(--accent-red);font-size:13px;display:none"></p>
      <button type="submit" style="width:100%;padding:12px;background:var(--accent-blue);color:#fff;border:none;border-radius:4px;font-size:14px;cursor:pointer;margin-top:12px">Login</button>
    </form>
  </div>
  <script src="login.js"></script>
</body>
</html>
```

`login.js`:
```javascript
document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const password = document.getElementById('password').value;
  const errorEl = document.getElementById('error');
  errorEl.style.display = 'none';

  try {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
      credentials: 'include',  // send/receive cookies
    });
    if (resp.ok) {
      window.location.href = 'dashboard.html';
    } else {
      errorEl.textContent = 'Invalid password';
      errorEl.style.display = 'block';
    }
  } catch (err) {
    errorEl.textContent = 'Connection error';
    errorEl.style.display = 'block';
  }
});
```

### Step 3: Dashboard HTML — 4 Tabs (1.5h)

`dashboard.html` skeleton:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ads Copilot — Dashboard</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header style="padding:16px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
    <h1 style="margin:0;font-size:18px">Ads Copilot</h1>
    <span id="last-updated" style="color:var(--text-secondary);font-size:13px"></span>
  </header>

  <main style="padding:24px;max-width:1200px;margin:0 auto">
    <!-- Tab Navigation -->
    <nav class="tab-nav">
      <button class="tab-btn active" data-tab="overview">Campaign Overview</button>
      <button class="tab-btn" data-tab="leads">Lead Metrics</button>
      <button class="tab-btn" data-tab="copy">Ad Copy & Keywords</button>
      <button class="tab-btn" data-tab="budget">Budget Tracking</button>
    </nav>

    <!-- Tab 1: Campaign Overview -->
    <div id="tab-overview" class="tab-panel active">
      <div class="kpi-grid">
        <div class="kpi-card"><div class="label">Impressions</div><div class="value" id="kpi-impressions">-</div></div>
        <div class="kpi-card"><div class="label">Clicks</div><div class="value" id="kpi-clicks">-</div></div>
        <div class="kpi-card"><div class="label">CTR</div><div class="value" id="kpi-ctr">-</div></div>
        <div class="kpi-card"><div class="label">Avg CPC</div><div class="value" id="kpi-cpc">-</div></div>
        <div class="kpi-card"><div class="label">Conversions</div><div class="value" id="kpi-conversions">-</div></div>
        <div class="kpi-card"><div class="label">CPL</div><div class="value" id="kpi-cpl">-</div></div>
        <div class="kpi-card"><div class="label">Total Spend</div><div class="value" id="kpi-spend">-</div></div>
        <div class="kpi-card"><div class="label">Conv Rate</div><div class="value" id="kpi-conv-rate">-</div></div>
      </div>
      <div class="chart-container"><canvas id="chart-performance-trend"></canvas></div>
      <div class="chart-container"><canvas id="chart-campaign-comparison"></canvas></div>
      <div class="chart-container" id="top-keywords-table"></div>
    </div>

    <!-- Tab 2: Lead Metrics -->
    <div id="tab-leads" class="tab-panel">
      <div class="kpi-grid">
        <div class="kpi-card"><div class="label">Leads Today</div><div class="value" id="kpi-leads-today">-</div></div>
        <div class="kpi-card"><div class="label">Leads This Week</div><div class="value" id="kpi-leads-week">-</div></div>
        <div class="kpi-card"><div class="label">Leads All Time</div><div class="value" id="kpi-leads-all">-</div></div>
        <div class="kpi-card"><div class="label">Avg Quality Score</div><div class="value" id="kpi-quality">-</div></div>
      </div>
      <div class="chart-container"><canvas id="chart-lead-trend"></canvas></div>
      <div class="chart-container"><canvas id="chart-lead-sources"></canvas></div>
    </div>

    <!-- Tab 3: Ad Copy & Keywords -->
    <div id="tab-copy" class="tab-panel">
      <h3 style="margin-top:0">Best Performing Ad Copy</h3>
      <div id="best-ad-copy"></div>
      <h3>Keyword Performance</h3>
      <div class="chart-container" id="keyword-table"></div>
      <h3>Optimization Suggestions</h3>
      <div id="optimization-suggestions"></div>
    </div>

    <!-- Tab 4: Budget Tracking -->
    <div id="tab-budget" class="tab-panel">
      <div class="kpi-card" style="margin-bottom:24px">
        <div class="label">Monthly Budget</div>
        <div class="value" id="budget-total">$500.00</div>
        <div class="progress-bar" style="margin-top:12px">
          <div class="progress-fill" id="budget-progress" style="width:0%;background:var(--accent-green)"></div>
        </div>
        <div style="margin-top:8px;color:var(--text-secondary);font-size:13px">
          <span id="budget-spent">$0.00</span> spent of <span id="budget-remaining">$500.00</span> remaining
        </div>
      </div>
      <div class="kpi-grid">
        <div class="kpi-card"><div class="label">Daily Average</div><div class="value" id="budget-daily-avg">-</div></div>
        <div class="kpi-card"><div class="label">Today's Spend</div><div class="value" id="budget-today">-</div></div>
        <div class="kpi-card"><div class="label">Pacing</div><div class="value" id="budget-pacing">-</div></div>
        <div class="kpi-card"><div class="label">EOM Forecast</div><div class="value" id="budget-forecast">-</div></div>
      </div>
      <div class="chart-container"><canvas id="chart-spend-trend"></canvas></div>
    </div>
  </main>

  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <script src="auth.js"></script>
  <script>if (!checkAuth()) throw new Error('redirecting');</script>
  <script src="charts.js"></script>
  <script src="dashboard.js"></script>
</body>
</html>
```

### Step 4: Dashboard JS — API Calls + Tab Logic (1.5h)

`dashboard.js`:
```javascript
const API_BASE = window.location.origin;
const REFRESH_INTERVAL = 15 * 60 * 1000; // 15 minutes

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
  });
});

// Fetch all data
async function loadAll() {
  try {
    const [metrics, leads, budget, keywords] = await Promise.all([
      fetchWithAuth('/api/metrics'),
      fetchWithAuth('/api/leads'),
      fetchWithAuth('/api/budget'),
      fetchWithAuth('/api/keywords'),
    ]);

    renderOverview(metrics);
    renderLeads(leads);
    renderBudget(budget);
    renderCopyKeywords(keywords);

    document.getElementById('last-updated').textContent =
      `Updated: ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    console.error('Failed to load data:', err);
    if (err.status === 401) window.location.href = 'index.html';
  }
}

async function fetchWithAuth(path) {
  const resp = await fetch(API_BASE + path, { credentials: 'include' });
  if (resp.status === 401) {
    // Try refresh
    const refresh = await fetch(API_BASE + '/api/auth/refresh', { method: 'POST', credentials: 'include' });
    if (refresh.ok) return fetch(API_BASE + path, { credentials: 'include' }).then(r => { if (!r.ok) throw r; return r.json(); });
    window.location.href = 'index.html';
    throw new Error('unauthorized');
  }
  if (!resp.ok) throw resp;
  return resp.json();
}

// Render functions
function renderOverview(data) {
  const { kpis, trend, campaigns, top_keywords } = data;

  // MULTI-CAMPAIGN: Account-level KPIs (secondary)
  // Per-campaign rows are the PRIMARY view (rendered as table below)
  document.getElementById('kpi-impressions').textContent = formatNumber(kpis.total_impressions);
  document.getElementById('kpi-clicks').textContent = formatNumber(kpis.total_clicks);
  document.getElementById('kpi-ctr').textContent = kpis.ctr + '%';
  // NOTE: avg_cpc computed as total_cost/total_clicks (NOT avg of per-campaign CPCs)
  document.getElementById('kpi-cpc').textContent = '$' + kpis.cpc.toFixed(2);
  document.getElementById('kpi-conversions').textContent = kpis.total_conversions;
  document.getElementById('kpi-cpl').textContent = kpis.cpl.toFixed(2);
  document.getElementById('kpi-spend').textContent = '$' + kpis.total_cost.toFixed(2);
  document.getElementById('kpi-conv-rate').textContent = kpis.conv_rate + '%';

  // Per-campaign table (PRIMARY VIEW — replaces aggregate comparison)
  renderPerCampaignTable(campaigns);

  // Empty state
  if (!trend || trend.length === 0) {
    showEmptyState('tab-overview');
    return;
  }

  // Performance trend chart (30-day multi-line, one line per campaign)
  renderPerformanceTrend(trend);
  // Top keywords table
  renderTopKeywordsTable(top_keywords);
}

function renderBudget(data) {
  const { per_campaign_pacing, account_totals } = data;

  // MULTI-CAMPAIGN: per-campaign pacing rows (primary), account total (secondary)
  renderPerCampaignPacingTable(per_campaign_pacing);

  // Account total summary
  const b = account_totals;
  const pct = Math.min((b.spent / b.total) * 100, 100);

  document.getElementById('budget-total').textContent = '$' + b.total.toFixed(2);
  document.getElementById('budget-spent').textContent = '$' + b.spent.toFixed(2);
  document.getElementById('budget-remaining').textContent = '$' + (b.total - b.spent).toFixed(2);
  document.getElementById('budget-progress').style.width = pct + '%';

  // Color code: green <60%, yellow 60-90%, red >90%
  const fill = document.getElementById('budget-progress');
  fill.style.background = pct > 90 ? 'var(--accent-red)' : pct > 60 ? 'var(--accent-yellow)' : 'var(--accent-green)';

  document.getElementById('budget-daily-avg').textContent = '$' + pacing.daily_avg.toFixed(2);
  document.getElementById('budget-today').textContent = '$' + pacing.today_spend.toFixed(2);
  document.getElementById('budget-pacing').textContent = pacing.pacing_pct.toFixed(0) + '%';
  document.getElementById('budget-forecast').textContent = '$' + forecast.end_of_month.toFixed(2);

  // Pacing color
  const pacingEl = document.getElementById('budget-pacing');
  pacingEl.style.color = pacing.pacing_pct > 120 ? 'var(--accent-red)' : pacing.pacing_pct > 100 ? 'var(--accent-yellow)' : 'var(--accent-green)';

  renderSpendTrend(data.spend_trend);
}

function showEmptyState(tabId) {
  const tab = document.getElementById(tabId);
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.innerHTML = '<div class="icon">📊</div><p>No data yet. Create your first campaign to see metrics here.</p>';
  // Insert after KPI grid, hide chart containers
  tab.querySelectorAll('.chart-container').forEach(c => c.style.display = 'none');
  tab.querySelector('.kpi-grid').after(empty);
}

function formatNumber(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return n.toString();
}

// Initial load + auto-refresh
loadAll();
setInterval(loadAll, REFRESH_INTERVAL);
```

### Step 5: Charts Configuration (1.5h)

`charts.js`:
```javascript
// Chart.js global defaults for dark theme
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = '#30363d';
Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';

const CHART_COLORS = {
  blue: '#58a6ff',
  green: '#3fb950',
  red: '#f85149',
  yellow: '#d29922',
  purple: '#bc8cff',
  orange: '#f0883e',
  cyan: '#39d2c0',
};

function renderPerformanceTrend(trend) {
  const ctx = document.getElementById('chart-performance-trend');
  if (!trend || trend.length === 0) return;

  new Chart(ctx, {
    type: 'line',
    data: {
      labels: trend.map(d => d.date),
      datasets: [
        { label: 'Clicks', data: trend.map(d => d.clicks), borderColor: CHART_COLORS.blue, fill: false, tension: 0.3 },
        { label: 'Conversions', data: trend.map(d => d.conversions), borderColor: CHART_COLORS.green, fill: false, tension: 0.3, yAxisID: 'y1' },
      ],
    },
    options: {
      responsive: true,
      interaction: { intersect: false, mode: 'index' },
      scales: { y: { beginAtZero: true }, y1: { position: 'right', beginAtZero: true } },
    },
  });
}

function renderPerCampaignTable(campaigns) {
  // MULTI-CAMPAIGN: per-campaign table is PRIMARY view on Tab 1
  // Each row shows campaign-specific KPIs, not aggregate averages
  const tbody = document.getElementById('campaign-table-body');
  if (!campaigns || campaigns.length === 0) return;

  tbody.innerHTML = campaigns.map(c => {
    const statusClass = c.status === 'active' ? 'status-active' : 'status-paused';
    const pacingClass = c.pacing_pct > 110 ? 'pacing-over' : (c.pacing_pct < 90 ? 'pacing-under' : 'pacing-ok');
    return `<tr>
      <td>${c.name}<br><small class="${statusClass}">${c.status} · ${c.objective}</small></td>
      <td>${formatNumber(c.impressions)}</td>
      <td>${formatNumber(c.clicks)}</td>
      <td>${c.ctr}%</td>
      <td>$${c.cpc.toFixed(2)}</td>
      <td>${c.has_conversion_tracking ? c.conversions + ' <small>$' + c.cpl.toFixed(2) + '</small>' : 'N/A'}</td>
      <td class="${pacingClass}">${c.pacing_pct}%</td>
    </tr>`;
  }).join('');
}

// Legacy campaign comparison chart (optional, secondary visualization)
function renderCampaignComparison(campaigns) {
  const ctx = document.getElementById('chart-campaign-comparison');
  if (!campaigns || campaigns.length === 0) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: campaigns.map(c => c.name),
      datasets: [
        { label: 'Cost ($)', data: campaigns.map(c => c.cost), backgroundColor: CHART_COLORS.blue },
        { label: 'Conversions', data: campaigns.map(c => c.conversions || 0), backgroundColor: CHART_COLORS.green },
      ],
    },
    options: { responsive: true, scales: { y: { beginAtZero: true } } },
  });
}

function renderSpendTrend(trend) {
  const ctx = document.getElementById('chart-spend-trend');
  if (!trend || trend.length === 0) return;

  // Add daily average reference line
  const avg = trend.reduce((sum, d) => sum + d.spend, 0) / trend.length;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: trend.map(d => d.date),
      datasets: [
        { label: 'Daily Spend', data: trend.map(d => d.spend), backgroundColor: CHART_COLORS.blue },
        { label: 'Daily Average', data: trend.map(() => avg), type: 'line', borderColor: CHART_COLORS.yellow, borderDash: [5, 5], pointRadius: 0, fill: false },
      ],
    },
    options: { responsive: true, scales: { y: { beginAtZero: true, title: { display: true, text: 'Spend ($)' } } } },
  });
}
```

### Step 6: Deploy to Cloudflare Pages (30 min)

```bash
cd ads-copilot-dashboard

# Deploy via wrangler Pages
npx wrangler pages deploy . --project-name=ads-copilot-dashboard

# Or connect to Git repo for auto-deploy
# Cloudflare Dashboard → Pages → Create → Connect to Git
```

**Workers + Pages routing**: configure custom domain and ensure `/api/*` requests
proxy to the Workers API (same worker, or Pages Functions if preferred).

## Todo
- [ ] Create `style.css` — dark theme, KPI cards, tabs, tables, progress bar, responsive
- [ ] Create `index.html` — login page with password form
- [ ] Create `login.js` — POST /api/auth/login → set cookie → redirect
- [ ] Create `auth.js` — JWT cookie check, auto-refresh, redirect on expiry
- [ ] Create `dashboard.html` — 4 tabs with all KPI cards, chart canvases, table containers
- [ ] Create `dashboard.js` — tab switching, parallel API fetch, render functions, 15min polling
- [ ] Create `charts.js` — Chart.js configs (performance trend multi-line, campaign comparison, spend trend, lead sources)
- [ ] Implement per-campaign table on Tab 1 (primary view, not just aggregate KPIs)
- [ ] Implement per-campaign pacing table on Tab 4 (primary view, not just account total)
- [ ] Multi-line trend chart (one line per campaign, not aggregated)
- [ ] Implement empty state handling for all 4 tabs
- [ ] Implement error handling (401 → redirect to login, network error → show message)
- [ ] Test: login flow (correct password, wrong password)
- [ ] Test: all 4 tabs render with seeded D1 data
- [ ] Test: empty state when 0 campaigns exist
- [ ] Test: responsive layout on mobile viewport
- [ ] Deploy to Cloudflare Pages
- [ ] Configure Pages → Workers API routing

## Success Criteria
- Login page renders → enter password → get JWT cookie → redirect to dashboard
- Wrong password → error message, no redirect
- Dashboard loads with 4 tabs, default tab = Campaign Overview
- Per-campaign table shown on Tab 1 (each campaign with its own KPIs)
- Per-campaign pacing shown on Tab 4 (each campaign with its own pacing %)
- Avg CPC computed as total_cost/total_clicks (NOT avg of per-campaign CPCs)
- Campaigns without conversion tracking show "N/A" for CPL/conversions columns
- Tab switching works without page reload
- KPI cards display correct values from D1 API
- Chart.js charts render correctly (line, bar, doughnut)
- Empty state ("No data yet") shown when 0 campaigns
- 15min auto-refresh works (verify in browser Network tab)
- Mobile-responsive: works on 375px viewport
- Page loads <2s on 4G connection (excluding Chart.js CDN)
- Budget progress bar colors: green <60%, yellow 60-90%, red >90%

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| Auth bypass (H4) | High | JWT checked on every API call. httpOnly cookie (not localStorage). Server-side verification. |
| JWT theft (H6) | Med | httpOnly + Secure + SameSite=Strict. Revocation table. 24h expiry. |
| Chart.js CDN blocked | Low | Pinned version. Document local fallback (download chart.umd.min.js). |
| Empty state breaks layout | Med | Test with 0 data. Guard all render functions. Show friendly message. |
| Workers cold start on API | Low | Dashboard fetches 4 endpoints in parallel. Cold start ~50ms. Users won't notice. |

## Security
- JWT in httpOnly, Secure, SameSite=Strict cookie
- No sensitive data in localStorage or URL params
- CORS restricted to Pages origin only
- Login rate limit (Workers middleware — suggest adding to Phase 02 if not already)
- No user input rendered as raw HTML (all via textContent)

## Next Steps
- Phase 06 (integration testing) — verify full flow: data in D1 → dashboard renders correctly
