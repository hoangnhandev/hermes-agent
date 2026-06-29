#!/usr/bin/env python3
"""Dashboard render engine — metrics dict → HTML string.

Reads templates/dashboard.html.tpl, injects JSON metrics (XSS-safe via
json.dumps) and substitute variables. All untrusted text (questions,
rationale, categories) is escaped client-side by the template's JS —
the only server-side interpolation is the JSON blob (safe in <script>).

Server-side: html.escape on edge_threshold display; json.dumps for data.
"""

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from _dashboard_data import MIN_RESOLVED_FOR_CALIBRATION, EDGE_THRESHOLD

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def build_html(metrics: dict, template_path: Path | str | None = None) -> str:
    """Render metrics dict into a complete dashboard HTML string."""
    if template_path is None:
        template_path = TEMPLATES_DIR / "dashboard.html.tpl"
    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    tpl = template_path.read_text(encoding="utf-8")

    # JSON data blob — json.dumps is safe inside <script type=application/json>
    # Strip </ sequences to prevent premature script close (JSON-in-HTML rule)
    json_data = json.dumps(metrics, default=str, ensure_ascii=False)
    json_data = json_data.replace("</", r"<\/")

    # Banner for insufficient calibration data
    resolved_count = metrics.get("resolved_count", 0)
    if resolved_count > 0 and resolved_count < MIN_RESOLVED_FOR_CALIBRATION:
        banner = (
            '<div class="banner">'
            f"Collecting resolved predictions ({resolved_count}/{MIN_RESOLVED_FOR_CALIBRATION} "
            "minimum) — calibration curve is not yet significant"
            "</div>"
        )
    elif resolved_count == 0 and metrics.get("total_predictions", 0) > 0:
        banner = (
            '<div class="banner">'
            "No resolved predictions yet — dashboard will populate as markets resolve"
            "</div>"
        )
    else:
        banner = ""

    # Edge threshold as escaped display string
    edge_display = html.escape(f"{EDGE_THRESHOLD * 100:.0f}")

    # Last updated timestamp (UTC)
    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    tmpl = Template(tpl)
    return tmpl.safe_substitute(
        JSON_DATA=json_data,
        BANNER=banner,
        LAST_UPDATED=last_updated,
        EDGE_THRESHOLD=edge_display,
    )
