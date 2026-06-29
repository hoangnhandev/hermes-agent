/* ============================================================
   utils.js — formatting, HTML escape, authed fetch, tab loading.
   Tab HTML is fetched once then cached; reloads come from cache
   so re-rendering a tab (after empty-state wipe or theme change)
   is synchronous and never re-hits the network.
   ============================================================ */

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return String(num);
}

// VND: no minor units, vi-VN digit grouping, ₫ suffix.
// (Ad spend amounts are stored as raw numbers; if the account is billed in
// VND these values are already VND — only the symbol was wrong before.)
const VND = new Intl.NumberFormat('vi-VN', {
  style: 'currency',
  currency: 'VND',
  maximumFractionDigits: 0,
});

function formatCurrency(amount) {
  return VND.format(Number(amount || 0));
}

function formatPercent(value) {
  return (Number(value || 0) * 100).toFixed(2) + '%';
}

/** Escape user/data strings before injecting as HTML. */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (m) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]
  ));
}

/** A single-cell empty row spanning all table columns. */
function emptyRow(colspan, text) {
  return (
    '<tr><td colspan="' + colspan + '" style="padding:0;">' +
    '<div class="empty-state"><span class="empty-icon">' + icon('database', { size: 36 }) + '</span>' +
    '<div class="empty-text">' + esc(text || 'No data available yet') + '</div></div></td></tr>'
  );
}

/** A standalone empty block for non-table containers. */
function emptyBlock(text) {
  return (
    '<div class="empty-state"><span class="empty-icon">' + icon('database', { size: 36 }) + '</span>' +
    '<div class="empty-text">' + esc(text || 'No data available yet') + '</div></div>'
  );
}

async function fetchWithAuth(path) {
  try {
    let response = await fetch(path, { credentials: 'include' });

    if (response.status === 401) {
      const refreshSuccess = await refreshAndRedirect();
      if (!refreshSuccess) throw new Error('Authentication failed');
      response = await fetch(path, { credentials: 'include' });
    }

    if (!response.ok) throw new Error('HTTP ' + response.status);
    return await response.json();
  } catch (error) {
    console.error('Fetch error:', error);
    throw error;
  }
}

const TAB_HTML_CACHE = {};

/** Fetch (once) and inject a tab's HTML fragment into its pane, then hydrate icons. */
async function loadTabContent(tabId) {
  try {
    let html = TAB_HTML_CACHE[tabId];
    if (html == null) {
      const response = await fetch('tab-' + tabId + '.html');
      if (!response.ok) return;
      html = await response.text();
      TAB_HTML_CACHE[tabId] = html;
    }
    // Inject into the pane itself ({id}-tab); tab fragments are bare content.
    const container = document.getElementById(tabId + '-tab');
    if (container && container.innerHTML !== html) {
      container.innerHTML = html;
      hydrateIcons(container);
    }
  } catch (error) {
    console.error('Failed to load ' + tabId + ' tab:', error);
  }
}

/** Replace a tab pane with a single empty-state card (data not yet synced). */
function showEmptyState(tabId, message) {
  const pane = document.getElementById(tabId + '-tab');
  if (!pane) return;
  pane.querySelectorAll('canvas').forEach((canvas) => {
    const chart = Chart.getChart(canvas);
    if (chart) chart.destroy();
  });
  pane.innerHTML =
    '<div class="section-card"><div class="empty-state">' +
    '<span class="empty-icon">' + icon('database', { size: 48 }) + '</span>' +
    '<div class="empty-title">No data yet</div>' +
    '<div class="empty-text">' + esc(message || 'Connect a Google Ads account and run a sync to see your metrics here.') + '</div>' +
    '</div></div>';
}

function updateLastUpdated() {
  const el = document.getElementById('lastUpdated');
  if (!el) return;
  const now = new Date();
  el.textContent = 'Updated ' + now.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
