/* ============================================================
   chart-tables.js — sortable data tables + spend-trend chart.
   Sort reads each cell's data-v (raw sortable value) so it never
   needs access to the source array — works on rendered rows.
   ============================================================ */

/** Map a campaign/ad status string to a semantic badge. */
function statusBadge(status) {
  const s = String(status || '').toUpperCase();
  let cls = 'badge-neutral';
  if (['ENABLED', 'ACTIVE', 'ELIGIBLE', 'SERVING', 'APPROVED'].includes(s)) cls = 'badge-success';
  else if (['PAUSED', 'PENDING', 'IN_REVIEW', 'REVIEW'].includes(s)) cls = 'badge-warning';
  else if (['REMOVED', 'ENDED', 'REJECTED', 'DISAPPROVED'].includes(s)) cls = 'badge-danger';
  return '<span class="badge ' + cls + '">' + esc(status || '—') + '</span>';
}

/** Pacing text colored by severity (>110 over, <90 under). */
function pacingClass(percent) {
  return percent > 110 ? 'text-danger' : percent < 90 ? 'text-warning' : 'text-success';
}

/** Wire click-to-sort on every .th-sort header of a table. */
function setupTableSort(table) {
  if (!table || table.dataset.sortReady) return;
  table.dataset.sortReady = '1';
  const headers = table.querySelectorAll('th.th-sort');

  headers.forEach((th) => {
    th.addEventListener('click', () => {
      const tbody = table.tBodies[0];
      if (!tbody) return;
      const type = th.dataset.sortType || 'string';
      const dir = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
      const colIndex = [].indexOf.call(th.parentElement.children, th);

      headers.forEach((h) => {
        h.setAttribute('aria-sort', 'none');
        const ind = h.querySelector('.sort-ind');
        if (ind) ind.innerHTML = '';
      });
      th.setAttribute('aria-sort', dir);
      const ind = th.querySelector('.sort-ind');
      if (ind) ind.innerHTML = icon(dir === 'ascending' ? 'sort-up' : 'sort-down', { size: 14 });

      const rows = [].slice.call(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {
        const ca = a.children[colIndex];
        const cb = b.children[colIndex];
        const av = (ca && (ca.getAttribute('data-v') !== null ? ca.getAttribute('data-v') : ca.textContent)) || '';
        const bv = (cb && (cb.getAttribute('data-v') !== null ? cb.getAttribute('data-v') : cb.textContent)) || '';
        let cmp;
        if (type === 'number') {
          cmp = (parseFloat(av) || 0) - (parseFloat(bv) || 0);
        } else {
          cmp = String(av).localeCompare(String(bv));
        }
        return dir === 'ascending' ? cmp : -cmp;
      });
      rows.forEach((r) => tbody.appendChild(r));
    });
  });
}

function renderPerCampaignTable(campaigns) {
  const tbody = document.getElementById('campaignTableBody');
  if (!tbody) return;
  if (!campaigns || campaigns.length === 0) {
    tbody.innerHTML = emptyRow(10, 'No campaign data available');
    return;
  }

  tbody.innerHTML = campaigns.map((c) => {
    const ctr = c.impressions ? c.clicks / c.impressions : 0;
    const cpl = c.conversions > 0 ? c.cost / c.conversions : null;
    return (
      '<tr>' +
      '<td data-v="' + esc(c.name) + '">' + esc(c.name) + '</td>' +
      '<td>' + statusBadge(c.status) + '</td>' +
      '<td data-v="' + esc(c.objective) + '">' + esc(c.objective || '—') + '</td>' +
      '<td class="t-num" data-v="' + c.impressions + '">' + formatNumber(c.impressions) + '</td>' +
      '<td class="t-num" data-v="' + c.clicks + '">' + formatNumber(c.clicks) + '</td>' +
      '<td class="t-num" data-v="' + (ctr * 100).toFixed(2) + '">' + (ctr * 100).toFixed(2) + '%</td>' +
      '<td class="t-num" data-v="' + c.cpc.toFixed(2) + '">' + formatCurrency(c.cpc) + '</td>' +
      '<td class="t-num" data-v="' + (c.conversions || 0) + '">' + (c.conversions || 'N/A') + '</td>' +
      '<td class="t-num" data-v="' + (cpl !== null ? cpl.toFixed(2) : '') + '">' + (cpl === null ? 'N/A' : formatCurrency(cpl)) + '</td>' +
      '<td class="t-num ' + pacingClass(c.pacing) + '" data-v="' + c.pacing + '">' + c.pacing.toFixed(1) + '%</td>' +
      '</tr>'
    );
  }).join('');

  const table = document.getElementById('campaignTable');
  if (table) setupTableSort(table);
}

function renderTopKeywordsTable(keywords) {
  const tbody = document.getElementById('topKeywordsTableBody');
  if (!tbody) return;
  if (!keywords || keywords.length === 0) {
    tbody.innerHTML = emptyRow(6, 'No keyword data available');
    return;
  }

  tbody.innerHTML = keywords.slice(0, 10).map((k) => {
    const ctr = k.impressions ? k.clicks / k.impressions : 0;
    return (
      '<tr>' +
      '<td data-v="' + esc(k.text) + '">' + esc(k.text) + '</td>' +
      '<td class="t-num" data-v="' + k.impressions + '">' + formatNumber(k.impressions) + '</td>' +
      '<td class="t-num" data-v="' + k.clicks + '">' + formatNumber(k.clicks) + '</td>' +
      '<td class="t-num" data-v="' + (ctr * 100).toFixed(2) + '">' + (ctr * 100).toFixed(2) + '%</td>' +
      '<td class="t-num" data-v="' + k.cpc.toFixed(2) + '">' + formatCurrency(k.cpc) + '</td>' +
      '<td class="t-num" data-v="' + (k.conversions || 0) + '">' + (k.conversions || 0) + '</td>' +
      '</tr>'
    );
  }).join('');

  const table = document.getElementById('topKeywordsTable');
  if (table) setupTableSort(table);
}

function renderSpendTrend(trend) {
  destroyChartIfExists('spendTrendChart');
  if (!trend || trend.length === 0) return;

  const canvas = document.getElementById('spendTrendChart');
  if (!canvas) return;
  const palette = getChartTheme().palette;
  const avgSpend = trend.reduce((sum, item) => sum + item.spend, 0) / trend.length;

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: trend.map((item) => item.date),
      datasets: [
        { label: 'Daily Spend', data: trend.map((item) => item.spend), backgroundColor: palette[0], borderRadius: 4, maxBarThickness: 28 },
        { label: 'Daily Average', data: trend.map(() => avgSpend), type: 'line', borderColor: palette[2], backgroundColor: palette[2], borderWidth: 2, pointRadius: 0, tension: 0 },
      ],
    },
    options: baseChartOptions({
      scales: {
        x: { grid: { color: getChartTheme().grid }, ticks: { color: getChartTheme().text } },
        y: { grid: { color: getChartTheme().grid }, ticks: { color: getChartTheme().text }, title: { display: true, text: 'Spend (₫)', color: getChartTheme().textStrong }, beginAtZero: true },
      },
    }),
  });
}

function renderPerCampaignPacingTable(pacing) {
  const tbody = document.getElementById('pacingTableBody');
  if (!tbody) return;
  if (!pacing || pacing.length === 0) {
    tbody.innerHTML = emptyRow(5, 'No pacing data available');
    return;
  }

  tbody.innerHTML = pacing.map((c) => (
    '<tr>' +
    '<td data-v="' + esc(c.name) + '">' + esc(c.name) + '</td>' +
    '<td class="t-num" data-v="' + c.daily_budget.toFixed(2) + '">' + formatCurrency(c.daily_budget) + '</td>' +
    '<td class="t-num" data-v="' + c.spent.toFixed(2) + '">' + formatCurrency(c.spent) + '</td>' +
    '<td class="t-num ' + pacingClass(c.pacing_percent) + '" data-v="' + c.pacing_percent + '">' + c.pacing_percent.toFixed(1) + '%</td>' +
    '<td>' + statusBadge(c.status) + '</td>' +
    '</tr>'
  )).join('');

  const table = document.getElementById('pacingTable');
  if (table) setupTableSort(table);
}
