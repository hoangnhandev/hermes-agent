/* ============================================================
   render-functions.js — all tab renderers.
   KPI deltas render ONLY when the backend supplies comparison
   data (data.deltas); absent = hidden. No fabricated trends.
   ============================================================ */

/** Set a KPI value element's text. */
function setKpi(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

/**
 * Render a trend delta badge next to a KPI.
 * Accepts: number (sign = direction), or {value, direction:'up|down|flat'}.
 * Hides the badge when delta is null/undefined (backend has no comparison).
 */
function setKpiDelta(id, delta) {
  const el = document.getElementById(id + '-delta');
  if (!el) return;
  if (delta == null) { el.hidden = true; return; }

  let value;
  let dir;
  if (typeof delta === 'object') {
    value = Math.abs(Number(delta.value) || 0);
    dir = delta.direction || (value === 0 ? 'flat' : 'up');
  } else {
    value = Math.abs(Number(delta) || 0);
    dir = value === 0 ? 'flat' : delta >= 0 ? 'up' : 'down';
  }

  const cls = dir === 'up' ? 'up' : dir === 'down' ? 'down' : 'flat';
  const iconName = dir === 'up' ? 'trend-up' : dir === 'down' ? 'trend-down' : 'trend-flat';
  el.className = 'kpi-delta ' + cls;
  el.hidden = false;
  el.innerHTML = icon(iconName, { size: 12 }) + '<span>' + (value * 100).toFixed(1) + '%</span>';
}

/* ---------------- Overview ---------------- */
function renderOverview(data) {
  if (!data) { showEmptyState('overview'); return; }

  const account = data.account || {};
  setKpi('overview-impressions', formatNumber(account.impressions || 0));
  setKpi('overview-clicks', formatNumber(account.clicks || 0));
  setKpi('overview-ctr', formatPercent(account.ctr || 0));

  const avgCpc = account.clicks > 0 ? account.cost / account.clicks : 0;
  setKpi('overview-cpc', formatCurrency(avgCpc));
  setKpi('overview-conversions', account.conversions || 'N/A');

  const cpl = account.conversions > 0 ? account.cost / account.conversions : null;
  setKpi('overview-cpl', cpl ? formatCurrency(cpl) : 'N/A');
  setKpi('overview-spend', formatCurrency(account.cost || 0));

  const convRate = account.clicks > 0 ? account.conversions / account.clicks : 0;
  setKpi('overview-conv-rate', formatPercent(convRate));

  // Deltas (optional, backend-dependent). Keyed by KPI base id.
  const deltas = data.deltas || (account.deltas) || {};
  ['impressions', 'clicks', 'ctr', 'cpc', 'conversions', 'cpl', 'spend', 'conv-rate'].forEach((k) => {
    if (deltas[k] != null) setKpiDelta('overview-' + k, deltas[k]);
  });

  if (data.campaigns) renderPerCampaignTable(data.campaigns);
  if (data.trend) renderPerformanceTrend(data.trend);
  if (data.campaign_comparison) renderCampaignComparison(data.campaign_comparison);
  if (data.top_keywords) renderTopKeywordsTable(data.top_keywords);
}

/* ---------------- Leads ---------------- */
function renderLeads(data) {
  if (!data) { showEmptyState('leads'); return; }

  setKpi('leads-today', formatNumber(data.today || 0));
  setKpi('leads-week', formatNumber(data.week || 0));
  setKpi('leads-alltime', formatNumber(data.all_time || 0));
  setKpi('leads-quality', (data.avg_quality || 0).toFixed(2));

  const deltas = data.deltas || {};
  ['today', 'week', 'alltime', 'quality'].forEach((k) => {
    if (deltas[k] != null) setKpiDelta('leads-' + k, deltas[k]);
  });

  if (data.trend) renderLeadTrend(data.trend);
  if (data.sources) renderLeadSources(data.sources);
}

function renderLeadTrend(trend) {
  destroyChartIfExists('leadTrendChart');
  if (!trend || trend.length === 0) return;

  const canvas = document.getElementById('leadTrendChart');
  if (!canvas) return;
  const color = getChartTheme().palette[0];

  new Chart(canvas, {
    type: 'line',
    data: {
      labels: trend.map((item) => item.date),
      datasets: [{
        label: 'Leads',
        data: trend.map((item) => item.leads),
        borderColor: color,
        backgroundColor: color + '22',
        fill: true,
        tension: 0.35,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
      }],
    },
    options: baseChartOptions({
      scales: {
        x: { grid: { color: getChartTheme().grid }, ticks: { color: getChartTheme().text } },
        y: { grid: { color: getChartTheme().grid }, ticks: { color: getChartTheme().text }, title: { display: true, text: 'Leads', color: getChartTheme().textStrong } },
      },
    }),
  });
}

function renderLeadSources(sources) {
  destroyChartIfExists('leadSourcesChart');
  if (!sources || sources.length === 0) return;

  const canvas = document.getElementById('leadSourcesChart');
  if (!canvas) return;
  const palette = getChartTheme().palette;

  new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: sources.map((s) => s.source),
      datasets: [{
        data: sources.map((s) => s.leads),
        backgroundColor: sources.map((_, i) => palette[i % palette.length]),
        borderColor: getChartTheme().tooltipBg,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: { position: 'bottom', labels: { color: getChartTheme().textStrong, usePointStyle: true, boxWidth: 10 } },
        tooltip: {},
      },
    },
  });
}

/* ---------------- Keywords / Ad copy ---------------- */
function renderCopyKeywords(data) {
  if (!data) { showEmptyState('keywords'); return; }

  const best = document.getElementById('bestAdCopy');
  if (best) {
    if (data.best_ad_copy && data.best_ad_copy.length) {
      best.innerHTML = data.best_ad_copy.map((copy) => (
        '<div class="insight-card">' +
        '<div class="insight-title">' + esc(copy.headline) + '</div>' +
        '<div class="insight-desc">' + esc(copy.description) + '</div>' +
        '<div class="insight-meta"><span class="badge badge-success">CTR ' + formatPercent(copy.ctr) + '</span>' +
        '<span class="text-muted">Conversions: ' + (copy.conversions || 0) + '</span></div>' +
        '</div>'
      )).join('');
    } else {
      best.innerHTML = emptyBlock('No ad copy performance data yet');
    }
  }

  const tbody = document.getElementById('keywordPerformanceTableBody');
  if (tbody) {
    if (data.keywords && data.keywords.length) {
      tbody.innerHTML = data.keywords.slice(0, 10).map((k) => {
        const ctr = k.impressions ? k.clicks / k.impressions : 0;
        return (
          '<tr>' +
          '<td data-v="' + esc(k.text) + '">' + esc(k.text) + '</td>' +
          '<td class="t-num" data-v="' + k.impressions + '">' + formatNumber(k.impressions) + '</td>' +
          '<td class="t-num" data-v="' + k.clicks + '">' + formatNumber(k.clicks) + '</td>' +
          '<td class="t-num" data-v="' + (ctr * 100).toFixed(2) + '">' + (ctr * 100).toFixed(2) + '%</td>' +
          '<td class="t-num" data-v="' + k.cpc.toFixed(2) + '">$' + k.cpc.toFixed(2) + '</td>' +
          '<td class="t-num" data-v="' + (k.conversions || 0) + '">' + (k.conversions || 0) + '</td>' +
          '</tr>'
        );
      }).join('');
      const table = document.getElementById('keywordPerformanceTable');
      if (table) setupTableSort(table);
    } else {
      tbody.innerHTML = emptyRow(6, 'No keyword data available');
    }
  }

  const sug = document.getElementById('optimizationSuggestions');
  if (sug) {
    if (data.suggestions && data.suggestions.length) {
      sug.innerHTML = data.suggestions.map((s) => (
        '<div class="insight-card">' +
        '<div class="insight-meta"><span class="badge badge-info">' + esc(s.type) + '</span>' +
        (s.impact ? '<span class="badge badge-neutral">Impact: ' + esc(s.impact) + '</span>' : '') + '</div>' +
        '<div class="insight-desc">' + esc(s.description) + '</div>' +
        '</div>'
      )).join('');
    } else {
      sug.innerHTML = emptyBlock('No optimization suggestions yet');
    }
  }
}

/* ---------------- Budget ---------------- */
function renderBudget(data) {
  if (!data) { showEmptyState('budget'); return; }

  const wrap = document.getElementById('budgetProgressWrap');
  const bar = document.getElementById('budgetProgress');
  const pctEl = document.getElementById('budgetPercent');
  const totalEl = document.getElementById('totalBudget');
  if (data.monthly_budget && wrap && bar && pctEl && totalEl) {
    const percentUsed = (data.spent / data.monthly_budget) * 100;
    bar.style.width = Math.min(percentUsed, 100) + '%';
    bar.className = 'progress-bar ' + (percentUsed > 90 ? 'danger' : percentUsed > 60 ? 'warning' : '');
    pctEl.textContent = percentUsed.toFixed(1) + '%';
    totalEl.textContent = formatCurrency(data.monthly_budget);
    wrap.setAttribute('aria-valuenow', String(Math.round(Math.min(percentUsed, 100))));
  }

  setKpi('budget-daily-avg', formatCurrency(data.daily_average || 0));
  setKpi('budget-today', formatCurrency(data.today_spend || 0));
  setKpi('budget-forecast', formatCurrency(data.eom_forecast || 0));

  // Per-campaign pacing array (backend may use `pacing` or `pacing_table`).
  const pacingArr = Array.isArray(data.pacing) ? data.pacing : (Array.isArray(data.pacing_table) ? data.pacing_table : null);
  // Overall pacing KPI: explicit scalar, else average of per-campaign values.
  let overall = data.pacing_overall;
  if (overall == null && pacingArr && pacingArr.length) {
    overall = pacingArr.reduce((s, c) => s + (c.pacing_percent || 0), 0) / pacingArr.length / 100;
  }
  setKpi('budget-pacing', overall != null ? formatPercent(overall) : '--');

  if (data.spend_trend) renderSpendTrend(data.spend_trend);
  if (pacingArr) renderPerCampaignPacingTable(pacingArr);
}
