<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polymarket Signals — Calibration Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0e17;
    --surface: #111827;
    --surface-hover: #1a2234;
    --border: #1e293b;
    --border-accent: #2563eb22;
    --text: #e2e8f0;
    --text-dim: #64748b;
    --text-muted: #475569;
    --accent: #3b82f6;
    --accent-dim: #2563eb;
    --green: #22c55e;
    --green-dim: #16a34a33;
    --red: #ef4444;
    --red-dim: #dc262633;
    --yellow: #f59e0b;
    --yellow-dim: #f59e0b1a;
    --orange: #f97316;
    --radius: 12px;
    --radius-sm: 8px;
    --shadow: 0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3);
    --shadow-lg: 0 4px 20px rgba(0,0,0,0.5);
    --transition: 200ms ease-out;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    font-family: 'Fira Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Fade-in animation ── */
  @media (prefers-reduced-motion: no-preference) {
    .fade-in { animation: fadeIn 0.4s ease-out both; }
    .fade-in:nth-child(1) { animation-delay: 0ms; }
    .fade-in:nth-child(2) { animation-delay: 60ms; }
    .fade-in:nth-child(3) { animation-delay: 120ms; }
    .fade-in:nth-child(4) { animation-delay: 180ms; }
    .fade-in:nth-child(5) { animation-delay: 240ms; }
    .fade-in:nth-child(6) { animation-delay: 300ms; }
    .fade-in:nth-child(7) { animation-delay: 360ms; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  }
  @media (prefers-reduced-motion: reduce) {
    .fade-in { animation: none !important; opacity: 1; }
  }

  /* ── Layout ── */
  .container { max-width: 1440px; margin: 0 auto; padding: 24px; }

  /* ── Header ── */
  .header {
    text-align: center;
    padding: 32px 0 24px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 28px;
  }
  .header h1 {
    font-size: 1.6rem;
    font-weight: 600;
    color: var(--text);
    letter-spacing: -0.02em;
    margin-bottom: 4px;
  }
  .header h1 span { color: var(--accent); }
  .header .subtitle {
    font-size: 0.85rem;
    color: var(--text-dim);
    font-weight: 400;
  }

  /* ── KPI Stats Row ── */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    position: relative;
    overflow: hidden;
    transition: border-color var(--transition);
  }
  .stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--accent);
    opacity: 0.6;
  }
  .stat-card:hover { border-color: var(--accent-dim); }
  .stat-card .stat-label {
    font-size: 0.7rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-dim);
    margin-bottom: 6px;
  }
  .stat-card .stat-value {
    font-family: 'Fira Code', monospace;
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text);
  }
  .stat-card .stat-value.collecting { color: var(--yellow); font-size: 1rem; }

  /* ── Banner ── */
  .banner {
    background: var(--yellow-dim);
    border: 1px solid #f59e0b44;
    color: var(--yellow);
    text-align: center;
    padding: 12px 20px;
    border-radius: var(--radius-sm);
    margin-bottom: 20px;
    font-size: 0.85rem;
    font-weight: 500;
  }

  /* ── Grid ── */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
    gap: 20px;
  }
  @media (max-width: 560px) { .grid { grid-template-columns: 1fr; } }

  /* ── Panel ── */
  .panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
    transition: border-color var(--transition);
  }
  .panel:hover { border-color: #2563eb33; }
  .panel-wide { grid-column: 1 / -1; }
  .panel-title {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--accent);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .panel-title svg { width: 16px; height: 16px; opacity: 0.7; }
  .panel-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
    margin-left: 8px;
  }

  /* ── Tables ── */
  .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th {
    text-align: left;
    color: var(--text-dim);
    font-weight: 500;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid #1e293b55;
    font-family: 'Fira Code', monospace;
    font-size: 0.8rem;
    max-width: 260px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  tr:hover td { background: var(--surface-hover); }
  .td-text {
    font-family: 'Fira Sans', sans-serif;
    font-size: 0.82rem;
  }
  .edge-pos { color: var(--green); font-weight: 500; }
  .edge-neg { color: var(--red); font-weight: 500; }
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  .badge-green { background: var(--green-dim); color: var(--green); }
  .badge-red { background: var(--red-dim); color: var(--red); }
  .badge-yellow { background: var(--yellow-dim); color: var(--yellow); }

  /* ── Empty State ── */
  .empty-state {
    text-align: center;
    color: var(--text-dim);
    padding: 48px 20px;
  }
  .empty-state svg { margin-bottom: 12px; opacity: 0.4; }
  .empty-state .empty-title {
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--text-muted);
    margin-bottom: 4px;
  }
  .empty-state .empty-desc {
    font-size: 0.8rem;
    color: var(--text-dim);
  }

  /* ── Footer ── */
  .footer {
    text-align: center;
    color: var(--text-muted);
    font-size: 0.72rem;
    margin-top: 40px;
    padding: 20px 0;
    border-top: 1px solid var(--border);
  }
  .footer a { color: var(--accent); text-decoration: none; }
  .footer a:hover { text-decoration: underline; }

  /* ── Plotly overrides ── */
  .js-plotly-plot .plotly .modebar { display: none !important; }
</style>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" crossorigin="anonymous"></script>
<script id="__METRICS__" type="application/json">$JSON_DATA</script>
</head>
<body>
<noscript>
  <div style="text-align:center;color:#64748b;padding:80px 20px;font-family:sans-serif">
    <h2>JavaScript Required</h2>
    <p>This dashboard requires JavaScript to render charts.</p>
  </div>
</noscript>
<div class="container">
  <header class="header">
    <h1>Polymarket <span>Signals</span></h1>
    <p class="subtitle">Calibration Dashboard</p>
  </header>

  $BANNER

  <div class="stats-row" id="header-stats" aria-label="Key performance indicators"></div>

  <div class="grid">
    <div class="panel panel-wide fade-in" id="panel-calibration" role="img" aria-label="Calibration curve chart">
      <div class="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
        Calibration Curve
      </div>
      <div id="chart-calibration"></div>
    </div>

    <div class="panel fade-in" id="panel-brier-bar" role="img" aria-label="Brier score by category chart">
      <div class="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="12" width="4" height="9" rx="1"/><rect x="10" y="7" width="4" height="14" rx="1"/><rect x="17" y="3" width="4" height="18" rx="1"/></svg>
        Brier Score by Category
      </div>
      <div id="chart-brier-bar"></div>
    </div>

    <div class="panel fade-in" id="panel-brier-time" role="img" aria-label="Brier score over time chart">
      <div class="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        Brier Over Time
      </div>
      <div id="chart-brier-time"></div>
    </div>

    <div class="panel fade-in" id="panel-edge" role="img" aria-label="Edge distribution chart">
      <div class="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12h4l3-9 4 18 3-9h4"/></svg>
        Edge Distribution (LLM - Market)
      </div>
      <div id="chart-edge"></div>
    </div>

    <div class="panel fade-in" id="panel-active">
      <div class="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m22 12-4 4 4 4"/><path d="M6 12l4-4-4-4"/><circle cx="12" cy="12" r="4"/></svg>
        Active Signals (|edge| >= $EDGE_THRESHOLD%)
      </div>
      <div class="table-wrap" id="table-active"></div>
    </div>

    <div class="panel fade-in" id="panel-recent">
      <div class="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        Recent Predictions
      </div>
      <div class="table-wrap" id="table-recent"></div>
    </div>

    <div class="panel fade-in" id="panel-health">
      <div class="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
        Resolution Health
      </div>
      <div class="table-wrap" id="table-health"></div>
    </div>
  </div>

  <footer class="footer">
    Last updated: $LAST_UPDATED &middot; Generated by <a href="https://github.com/hoangnhandev/hermes-agent">Hermes</a> polymarket-signals
  </footer>
</div>

<script>
// ── Dashboard rendering engine ──
(function() {
  'use strict';
  var el = document.getElementById('__METRICS__');
  if (!el) return;
  var m = JSON.parse(el.textContent);

  // ── Design tokens (shared with CSS vars) ──
  var C = {
    bg: '#0a0e17', surface: '#111827', border: '#1e293b',
    text: '#e2e8f0', dim: '#64748b', muted: '#475569',
    accent: '#3b82f6', accentDim: '#2563eb',
    green: '#22c55e', red: '#ef4444', yellow: '#f59e0b', orange: '#f97316'
  };

  // ── Plotly dark theme ──
  var LAYOUT = {
    paper_bgcolor: C.surface,
    plot_bgcolor: C.surface,
    font: { family: "'Fira Sans', sans-serif", color: C.text, size: 12 },
    margin: { t: 20, b: 50, l: 55, r: 20 },
    xaxis: { gridcolor: '#1e293b55', zerolinecolor: '#334155', tickfont: { color: C.dim, family: "'Fira Code', monospace", size: 11 } },
    yaxis: { gridcolor: '#1e293b55', zerolinecolor: '#334155', tickfont: { color: C.dim, family: "'Fira Code', monospace", size: 11 } },
    legend: { bgcolor: C.surface, font: { color: C.dim, size: 11 }, borderwidth: 0 },
    showlegend: false
  };
  var CFG = { displayModeBar: false, responsive: true };

  // ── Helpers ──
  function fmtPct(v) { return v != null ? (v * 100).toFixed(1) + '%' : '—'; }
  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function tsShort(t) { return t ? t.replace('T', ' ').substring(0, 16) : '—'; }
  function emptyIcon() {
    return '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="' + C.muted + '" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 9h.01M15 9h.01M9 15h.01M15 15h.01"/></svg>';
  }
  function empty(title, desc) {
    return '<div class="empty-state">' + emptyIcon()
      + '<div class="empty-title">' + title + '</div>'
      + (desc ? '<div class="empty-desc">' + desc + '</div>' : '') + '</div>';
  }

  // ── Header KPI Cards ──
  (function() {
    var c = document.getElementById('header-stats');
    var brier = m.mean_brier;
    var items = [
      { label: 'Total Predictions', value: m.total_predictions || 0 },
      { label: 'Resolved', value: m.resolved_count || 0 },
      { label: 'Pending', value: m.pending_count || 0 },
      { label: 'Mean Brier', value: brier != null ? brier.toFixed(4) : null, cls: 'collecting', fallback: 'Collecting...' },
      { label: 'Last Scan', value: tsShort(m.last_scan_ts), cls: 'collecting' }
    ];
    c.innerHTML = items.map(function(i) {
      var v = i.value != null ? String(i.value) : i.fallback;
      var cls = (i.cls && (i.value == null)) ? ' ' + i.cls : '';
      return '<div class="stat-card fade-in"><div class="stat-label">' + i.label + '</div>'
        + '<div class="stat-value' + cls + '">' + v + '</div></div>';
    }).join('');
  })();

  // ── Calibration Curve ──
  (function() {
    var cal = m.calibration || [];
    var resolved = m.resolved_count || 0;
    var el = document.getElementById('chart-calibration');
    if (resolved < 30) {
      el.innerHTML = empty('Collecting data', resolved + '/30 resolved predictions needed for significant curve');
      return;
    }
    var bins = cal.filter(function(b) { return b.n > 0; });
    var mid = bins.map(function(b) { return (b.bin_lo + b.bin_hi) / 2; });
    var freq = bins.map(function(b) { return b.freq; });
    var ns = bins.map(function(b) { return b.n; });
    var traces = [
      { x: mid, y: freq, mode: 'markers+lines', name: 'Model',
        text: ns.map(function(n) { return 'n=' + n; }),
        marker: { size: ns.map(function(n) { return Math.min(18, Math.max(6, n * 0.8)); }), color: C.accent },
        line: { color: C.accent, width: 2 }, hovertemplate: 'Predicted: %{x:.0%}<br>Actual: %{y:.0%}<extra>n=%{text}</extra>' },
      { x: [0, 1], y: [0, 1], mode: 'lines', name: 'Perfect Cal.',
        line: { dash: 'dash', color: C.muted, width: 1 }, hoverinfo: 'skip' }
    ];
    Plotly.newPlot(el, traces, Object.assign({}, LAYOUT, {
      xaxis: Object.assign({}, LAYOUT.xaxis, { title: 'Predicted P', range: [0, 1], tickformat: '.0%' }),
      yaxis: Object.assign({}, LAYOUT.yaxis, { title: 'Actual Frequency', range: [0, 1], tickformat: '.0%' }),
      showlegend: true
    }), CFG);
  })();

  // ── Brier Bar (per-category) ──
  (function() {
    var bp = m.brier || {};
    var pc = bp.per_category || {};
    var cats = Object.keys(pc);
    var el = document.getElementById('chart-brier-bar');
    if (cats.length === 0) { el.innerHTML = empty('No data', 'Resolved predictions needed to compute Brier by category'); return; }
    var colors = cats.map(function(c) { return pc[c] <= 0.2 ? C.green : pc[c] <= 0.33 ? C.yellow : C.red; });
    Plotly.newPlot(el, [{ x: cats, y: cats.map(function(c) { return pc[c]; }),
      type: 'bar', marker: { color: colors, line: { color: C.surface, width: 1 } },
      hovertemplate: '%{x}<br>Brier: %{y:.4f}<extra></extra>' }],
      Object.assign({}, LAYOUT, {
        yaxis: Object.assign({}, LAYOUT.yaxis, { title: 'Brier Score', range: [0, Math.max(0.5, Math.ceil(Math.max.apply(null, cats.map(function(c) { return pc[c]; })) * 10) / 10 + 0.1)] })
      }), CFG);
  })();

  // ── Brier Over Time ──
  (function() {
    var rp = m.resolved_predictions || [];
    var el = document.getElementById('chart-brier-time');
    if (rp.length === 0) { el.innerHTML = empty('No data', 'Resolved predictions needed to track Brier over time'); return; }
    var weeks = {};
    rp.forEach(function(p) {
      if (!p.resolved_ts) return;
      var d = p.resolved_ts.substring(0, 10);
      if (!weeks[d]) weeks[d] = [];
      weeks[d].push(Math.pow(p.predicted_p - p.outcome_int, 2));
    });
    var dates = Object.keys(weeks).sort();
    var means = dates.map(function(d) {
      var errs = weeks[d];
      return errs.reduce(function(a, b) { return a + b; }, 0) / errs.length;
    });
    Plotly.newPlot(el, [{ x: dates, y: means, mode: 'lines+markers', name: 'Mean Brier',
      line: { color: C.orange, width: 2, shape: 'spline' },
      marker: { size: 6, color: C.orange },
      fill: 'tozeroy', fillcolor: 'rgba(249,115,22,0.08)',
      hovertemplate: '%{x}<br>Brier: %{y:.4f}<extra></extra>' }],
      Object.assign({}, LAYOUT, {
        yaxis: Object.assign({}, LAYOUT.yaxis, { title: 'Brier Score' }),
        xaxis: Object.assign({}, LAYOUT.xaxis, { title: null })
      }), CFG);
  })();

  // ── Edge Distribution ──
  (function() {
    var ed = m.edge_distribution || {};
    var hist = ed.histogram || [];
    var el = document.getElementById('chart-edge');
    if (hist.length === 0) { el.innerHTML = empty('No data', 'Predictions needed to compute edge distribution'); return; }
    var mid = hist.map(function(b) { return (b.bin_lo + b.bin_hi) / 2; });
    var colors = hist.map(function(b) { var v = (b.bin_lo + b.bin_hi) / 2; return v > 0 ? C.green : v < 0 ? C.red : C.muted; });
    Plotly.newPlot(el, [{ x: mid, y: hist.map(function(b) { return b.count; }),
      type: 'bar', marker: { color: colors, line: { color: C.surface, width: 1 } },
      hovertemplate: 'Edge: %{x:.1%}<br>Count: %{y}<extra></extra>' }],
      Object.assign({}, LAYOUT, {
        xaxis: Object.assign({}, LAYOUT.xaxis, { title: 'Edge (LLM − Market)', tickformat: '.0%' }),
        yaxis: Object.assign({}, LAYOUT.yaxis, { title: 'Count' })
      }), CFG);
  })();

  // ── Active Signals Table ──
  (function() {
    var sigs = m.active_signals || [];
    var el = document.getElementById('table-active');
    if (sigs.length === 0) { el.innerHTML = empty('No active signals', 'No predictions exceed the edge threshold'); return; }
    var h = '<table><thead><tr><th>Market</th><th>Category</th><th>LLM P</th><th>Market P</th><th>Edge</th><th>Scan</th></tr></thead><tbody>';
    sigs.forEach(function(s) {
      var cls = s.edge > 0 ? 'edge-pos' : 'edge-neg';
      var badgeCls = s.edge > 0 ? 'badge-green' : 'badge-red';
      h += '<tr><td class="td-text" title="' + esc(s.condition_id) + '">' + esc(s.question).substring(0, 55) + '</td>'
        + '<td>' + esc(s.category) + '</td>'
        + '<td>' + fmtPct(s.predicted_p) + '</td>'
        + '<td>' + fmtPct(s.market_p) + '</td>'
        + '<td><span class="badge ' + badgeCls + '">' + (s.edge > 0 ? '+' : '') + (s.edge * 100).toFixed(1) + '%</span></td>'
        + '<td>' + tsShort(s.scan_ts) + '</td></tr>';
    });
    h += '</tbody></table>';
    el.innerHTML = h;
  })();

  // ── Recent Predictions Table ──
  (function() {
    var rp = m.recent_predictions || [];
    var el = document.getElementById('table-recent');
    if (rp.length === 0) { el.innerHTML = empty('No predictions yet', 'Market scans will populate this table'); return; }
    var h = '<table><thead><tr><th>Market</th><th>Category</th><th>LLM P</th><th>Market P</th><th>Outcome</th><th>Result</th></tr></thead><tbody>';
    rp.forEach(function(r) {
      var resolved = r.outcome_int != null;
      var outcome = resolved ? (r.outcome_int === 1 ? 'Yes' : 'No') : 'Pending';
      var outcomeCls = resolved ? (r.outcome_int === 1 ? 'badge-green' : 'badge-red') : 'badge-yellow';
      var hit = resolved
        ? (Math.abs(r.predicted_p - r.outcome_int) < 0.5
          ? '<span class="badge badge-green">Hit</span>'
          : '<span class="badge badge-red">Miss</span>')
        : '<span class="badge badge-yellow">Pending</span>';
      h += '<tr><td class="td-text">' + esc(r.question).substring(0, 45) + '</td>'
        + '<td>' + esc(r.category) + '</td>'
        + '<td>' + fmtPct(r.predicted_p) + '</td>'
        + '<td>' + fmtPct(r.market_p) + '</td>'
        + '<td><span class="badge ' + outcomeCls + '">' + outcome + '</span></td>'
        + '<td>' + hit + '</td></tr>';
    });
    h += '</tbody></table>';
    el.innerHTML = h;
  })();

  // ── Resolution Health ──
  (function() {
    var h = m.resolution_health || {};
    var el = document.getElementById('table-health');
    var rows = [
      { label: 'Resolved', val: h.resolved || 0, cls: 'badge-green' },
      { label: 'Pending', val: h.pending || 0, cls: 'badge-yellow' },
      { label: 'Disputed', val: h.disputed_count || 0, cls: 'badge-red' }
    ];
    var html = '<table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>';
    rows.forEach(function(r) {
      html += '<tr><td class="td-text">' + r.label + '</td><td><span class="badge ' + r.cls + '">' + r.val + '</span></td></tr>';
    });
    html += '</tbody></table>';
    if (h.disputed && h.disputed.length > 0) {
      html += '<div style="margin-top:16px"><div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:' + C.yellow + ';margin-bottom:8px">Disputed Markets</div>';
      html += '<table><thead><tr><th>Market</th><th>Status</th></tr></thead><tbody>';
      h.disputed.forEach(function(d) {
        html += '<tr><td class="td-text">' + esc(d.question).substring(0, 55) + '</td><td><span class="badge badge-yellow">' + esc(d.resolution_status) + '</span></td></tr>';
      });
      html += '</tbody></table></div>';
    }
    el.innerHTML = html;
  })();

  // ── Responsive Plotly re-layout on resize ──
  var ro = new ResizeObserver(function() { Plotly.Plots.resize(document.querySelectorAll('.js-plotly-plot')); });
  document.querySelectorAll('.panel').forEach(function(p) { ro.observe(p); });
})();
</script>
</body>
</html>
