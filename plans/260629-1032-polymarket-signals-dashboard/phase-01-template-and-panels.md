# Phase 01 — HTML Template + 7 Panels + Plotly

## Context
- Parent: [plan.md](plan.md). Depends: phase-00 (`_dashboard_data.build_metrics()`).
- Scenario criticals: C1 (XSS), C6 (empty state). High: scale (#11/#12), Plotly CDN (#18), calibration-on-few (#39), unicode (#6).

## Overview
Render the metrics dict into a single dark-themed `dashboard.html` with 7 Plotly
panels via CDN. Generator = stdlib (string templating + `html.escape` + `json.dumps`).
Must be XSS-safe, scale-bounded, and degrade gracefully (empty state, no-JS).

## Key Insights
- **Untrusted text**: `predictions.rationale`, `markets.question` originate from Polymarket
  → treat as attacker-controlled. EVERY interpolation into HTML MUST go through `html.escape()`
  (C1, F-07 cousin). Data for Plotly traces via `json.dumps` (safe in `<script>` if not inside
  `</script>`; also escape `<`/`>` per JSON-in-HTML rule).
- **Scale**: never embed all raw rows. Calibration = fixed bins; recent table = paginated/capped
  (e.g. 50); edge histogram = pre-binned server-side. Keeps HTML <~1MB (scenario #11/#12).
- **Calibration on few points is misleading** (F-14 cousin): show `n` per bin + overall resolved
  count; when resolved < threshold (e.g. 30), render banner "collecting data — curve not
  significant" instead of/over the curve (scenario #39).

## Requirements
- **Functional**: 7 panels (below), dark theme, category toggle on calibration.
- **Non-functional**: fully static (openable via `file://`), Plotly via CDN pinned, `<200
  lines` per file (split renderer + template string), zero pip dep, no inline untrusted HTML.

## The 7 Panels (all backed by real schema)
1. **Header**: total / resolved / pending / last scan ts / mean Brier (or "collecting").
2. **Calibration curve** (per-category toggle): predicted_p bins vs actual freq + diagonal y=x.
3. **Brier**: per-category bar + Brier-over-time line (by resolved_ts week).
4. **Edge distribution**: histogram of `predicted_p − market_p`; axis labeled ("LLM > crowd").
5. **Active signals table**: pending predictions with |edge| > threshold (top N), escaped text.
6. **Recent predictions table**: question, category, predicted_p, market_p, outcome, hit/miss (cap 50).
7. **Resolution health**: resolved / pending / disputed counts + disputed list (surfaces F-06/F-09).

## Architecture
```
scripts/generate_dashboard.py   # orchestrator: data → render → atomic write dist/
scripts/_dashboard_render.py    # metrics dict → HTML string (template + Plotly traces)
templates/dashboard.html.tpl    # static skeleton (dark CSS, 7 panel containers, Plotly CDN)
dashboard/dist/dashboard.html   # generated artifact (gitignored)
```

## Related Code Files
- **Create**: `scripts/generate_dashboard.py`, `scripts/_dashboard_render.py`,
  `templates/dashboard.html.tpl`.
- **Reuse**: `_dashboard_data.build_metrics()`.

## Implementation Steps
1. `templates/dashboard.html.tpl`: dark theme CSS, grid layout (responsive → mobile, #17),
   7 `<div>` panel containers, `<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"
   integrity="..." crossorigin></script>` (**pinned** version, #32), `<noscript>` fallback (#19),
   a single `window.__METRICS__ = {{JSON}}` injection point.
2. `_dashboard_render.build_html(metrics)`:
   - Compute Plotly traces (calibration scatter+diagonal, brier bar/line, edge histogram) as
     Python dicts → `json.dumps` list. Strip/escape `</` sequences for safe embed.
   - Build escaped table rows (`html.escape` on every question/rationale/category — C1).
   - Empty-state branches: 0 predictions → friendly "No data yet"; 0 resolved → calibration
     panel shows "Collecting resolved history (need ~30)" (C6).
   - Render header numbers (Brier None → "collecting").
   - `string.Template.safe_substitute` to inject JSON + last-updated timestamp.
3. `generate_dashboard.py`:
   - `m = build_metrics()`; `html = build_html(m)`.
   - **Atomic write**: write `dist/dashboard.html.tmp` → `os.replace` to `dist/dashboard.html`
     (scenario #14/#25 — never serve a half-written file).
   - CLI: `python3 generate_dashboard.py [--out dist/dashboard.html]`. Print summary + exit 0/1.
   - Cap embedded data size; assert < threshold else warn.
4. Responsive: CSS grid collapses panels on narrow widths (#17).
5. Local view test: open `dist/dashboard.html` in browser; confirm all panels render with
   empty fixture AND a seeded fixture.

## Todo
- [ ] Template skeleton: dark CSS, 7 containers, pinned Plotly CDN, `<noscript>`
- [ ] `build_html()` with Plotly traces (calibration/brier/edge)
- [ ] XSS escape on ALL text interpolations (C1)
- [ ] Empty-state + zero-resolved banner (C6, #39)
- [ ] Scale caps (calib fixed bins, tables ≤50, pre-binned hist) (#11/#12)
- [ ] Atomic write temp→replace (#14/#25)
- [ ] Browser test: empty fixture + seeded fixture

## Success Criteria
- `python3 generate_dashboard.py` produces `dist/dashboard.html` opening cleanly offline (minus CDN).
- Inject `<script>alert(1)</script>` as a fake question → NOT executed (escaped). (C1)
- Empty metrics → no traceback, friendly empty state. (C6)
- Resolved <30 → calibration shows "insufficient data" banner. (#39)
- HTML artifact <~1MB with seeded fixture of 1k predictions. (#11/#12)

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| XSS via untrusted text | Crit | `html.escape` every interpolation + json.dumps for traces; review pass |
| Plotly CDN blocked at view time | High | Pin version; document optional local `plotly.min.js` bundle fallback |
| Calibration misleads on few points | High | n per bin + <30 banner (#39) |
| Mobile layout breaks | Med | Responsive CSS grid |

## Security
- **C1 mitigation = core of this phase.** Assume all Polymarket text is hostile.
- No cookies/storage; static only.

## Next Steps
- → phase-02: deploy `dist/dashboard.html` to Cloudflare Pages behind Access.
