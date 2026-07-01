/* ============================================================
   dashboard.js — orchestration: auth gate, nav switching,
   data fetching + tab-aware rendering.
   Fixes two latent bugs from the legacy version:
     1. Race — render ran before tab HTML was injected (null IDs).
        Now renderTab() awaits the (cached) tab HTML first.
     2. Charts rendered in hidden containers → 0px size.
        Now only the ACTIVE tab is rendered; switching re-renders.
   ============================================================ */

const TAB_TITLES = {
  overview: 'Campaign Overview',
  leads: 'Lead Metrics',
  'form-leads': 'Leads (Form)',
  keywords: 'Ad Copy & Keywords',
  budget: 'Budget Tracking',
};

// Data cache; re-rendered into whichever tab is active.
const DATA = { metrics: null, leads: null, 'form-leads': null, budget: null, keywords: null };
let activeTab = 'overview';

/** Ensure the tab's HTML is present (cached), then render its data. */
function renderTab(tabId) {
  return loadTabContent(tabId).then(() => {
    switch (tabId) {
      case 'overview': renderOverview(DATA.metrics); break;
      case 'leads': renderLeads(DATA.leads); break;
      case 'form-leads': renderFormLeads(DATA['form-leads']); break;
      case 'keywords': renderCopyKeywords(DATA.keywords); break;
      case 'budget': renderBudget(DATA.budget); break;
    }
  });
}

function switchTab(tabId) {
  activeTab = tabId;
  document.querySelectorAll('.nav-item[data-tab]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach((pane) => {
    pane.classList.toggle('active', pane.id === tabId + '-tab');
  });
  const title = document.getElementById('topbarTitle');
  if (title) title.textContent = TAB_TITLES[tabId] || tabId;
  renderTab(tabId);
}

function setupNav() {
  document.querySelectorAll('.nav-item[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
}

// Per-endpoint catch: a single failing endpoint degrades to an empty tab
// instead of blanking the whole dashboard. Auth redirect still fires via
// refreshAndRedirect() inside fetchWithAuth.
async function loadAll() {
  const [metrics, leads, formLeads, budget, keywords] = await Promise.all([
    fetchWithAuth('/api/metrics').catch(() => null),
    fetchWithAuth('/api/leads').catch(() => null),
    fetchWithAuth('/api/form-leads').catch(() => null),
    fetchWithAuth('/api/budget').catch(() => null),
    fetchWithAuth('/api/keywords').catch(() => null),
  ]);
  DATA.metrics = metrics;
  DATA.leads = leads;
  DATA['form-leads'] = formLeads;
  DATA.budget = budget;
  DATA.keywords = keywords;
  await renderTab(activeTab);
  updateLastUpdated();
}

function boot() {
  setupNav();

  // Manual refresh button (app.js dispatches 'ads:refresh').
  window.addEventListener('ads:refresh', (e) => {
    loadAll().finally(() => { if (e.detail && e.detail.done) e.detail.done(); });
  });

  // Theme toggle (app.js): re-apply Chart.js colors + re-render active tab
  // so its charts adopt the new palette immediately.
  window.addEventListener('themechange', () => {
    if (typeof applyChartDefaults === 'function') applyChartDefaults();
    renderTab(activeTab);
  });

  loadAll();
  setInterval(loadAll, 15 * 60 * 1000);
}

// Auth gate first — never load data when unauthenticated.
(async () => {
  if (!(await checkAuth())) {
    window.location.href = 'index.html';
    return;
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
