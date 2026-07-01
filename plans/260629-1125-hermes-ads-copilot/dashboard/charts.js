/* ============================================================
   charts.js — Chart.js theming + overview chart renderers.
   Colors are pulled from CSS variables so charts follow the
   active theme; applyChartDefaults() is re-run on themechange.
   ============================================================ */

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Theme-aware palette + text/grid colors for the current mode. */
function getChartTheme() {
  const palette = [];
  for (let i = 1; i <= 7; i++) {
    const c = cssVar('--chart-' + i);
    if (c) palette.push(c);
  }
  return {
    text: cssVar('--text-secondary'),
    textStrong: cssVar('--text-primary'),
    grid: cssVar('--border'),
    border: cssVar('--border'),
    font: cssVar('--font-sans'),
    tooltipBg: cssVar('--bg-elevated'),
    tooltipBorder: cssVar('--border-strong'),
    palette: palette.length ? palette : ['#4f8cff', '#34d399', '#fbbf24', '#38bdf8', '#f87171', '#a78bfa', '#f472b6'],
  };
}

/** Push current-theme colors into Chart.js global defaults. */
function applyChartDefaults() {
  const t = getChartTheme();
  Chart.defaults.font.family = t.font;
  Chart.defaults.font.size = 12;
  Chart.defaults.color = t.text;
  Chart.defaults.borderColor = t.border;
  Chart.defaults.scale.grid.color = t.grid;
  Chart.defaults.scale.ticks.color = t.text;
  Chart.defaults.scale.title.color = t.textStrong;
  Chart.defaults.plugins.legend.labels.color = t.textStrong;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  const tt = Chart.defaults.plugins.tooltip;
  tt.backgroundColor = t.tooltipBg;
  tt.titleColor = t.textStrong;
  tt.bodyColor = t.text;
  tt.borderColor = t.tooltipBorder;
  tt.borderWidth = 1;
  tt.padding = 10;
  tt.cornerRadius = 8;
  tt.boxPadding = 6;
  tt.displayColors = true;
  tt.usePointStyle = true;
}

applyChartDefaults();

function destroyChartIfExists(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (canvas) {
    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();
  }
}

/** Shared base options: responsive, fills parent height, themed axes. */
function baseChartOptions(extra) {
  const t = getChartTheme();
  return Object.assign({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: true, position: 'bottom', labels: { color: t.textStrong } },
      tooltip: {},
    },
    scales: {
      x: { grid: { color: t.grid }, ticks: { color: t.text }, border: { color: t.border } },
      y: { grid: { color: t.grid }, ticks: { color: t.text }, border: { color: t.border }, beginAtZero: true },
    },
  }, extra || {});
}

function renderPerformanceTrend(trend) {
  destroyChartIfExists('performanceTrendChart');
  if (!trend || trend.length === 0) return;

  const canvas = document.getElementById('performanceTrendChart');
  if (!canvas) return;
  const palette = getChartTheme().palette;

  // Category x-axis (avoids the date-adapter dependency that Chart.js v4
  // requires for the 'time' scale — which would otherwise throw at render).
  const labels = [...new Set(trend.map((item) => item.date))].sort();
  const campaigns = [...new Set(trend.map((item) => item.campaign))];

  const datasets = campaigns.map((campaign, index) => {
    const color = palette[index % palette.length];
    const byDate = {};
    trend.filter((item) => item.campaign === campaign)
      .forEach((item) => { byDate[item.date] = (byDate[item.date] || 0) + item.metric_value; });
    return {
      label: campaign,
      data: labels.map((d) => (byDate[d] != null ? byDate[d] : null)),
      borderColor: color,
      backgroundColor: color,
      tension: 0.35,
      fill: false,
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      spanGaps: true,
    };
  });

  new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: baseChartOptions({
      scales: {
        x: { grid: { color: getChartTheme().grid }, ticks: { color: getChartTheme().text }, title: { display: true, text: 'Date', color: getChartTheme().textStrong } },
        y: { grid: { color: getChartTheme().grid }, ticks: { color: getChartTheme().text }, title: { display: true, text: 'Clicks', color: getChartTheme().textStrong } },
      },
    }),
  });
}

function renderCampaignComparison(campaigns) {
  destroyChartIfExists('campaignComparisonChart');
  if (!campaigns || campaigns.length === 0) return;

  const canvas = document.getElementById('campaignComparisonChart');
  if (!canvas) return;
  const palette = getChartTheme().palette;

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: campaigns.map((c) => c.name),
      datasets: [
        { label: 'Cost', data: campaigns.map((c) => c.cost), backgroundColor: palette[4], borderRadius: 4, maxBarThickness: 36 },
        { label: 'Conversions', data: campaigns.map((c) => c.conversions), backgroundColor: palette[1], borderRadius: 4, maxBarThickness: 36 },
      ],
    },
    options: baseChartOptions(),
  });
}
