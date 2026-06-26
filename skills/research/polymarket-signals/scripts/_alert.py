#!/usr/bin/env python3
"""Alert formatting + computation for polymarket-signals.

Telegram-safe alert messages with mandatory uncalibrated disclaimer.
"""

import json

MAX_ALERT_LEN = 2000
MAX_RATIONALE_LEN = 500


def format_alert(prediction: dict, edge: float) -> str:
    """Format a Telegram-safe alert. MUST include uncalibrated disclaimer."""
    q = prediction.get("question", "Unknown market")
    yes_p = prediction.get("predicted_p")
    mkt_p = prediction.get("market_p")
    conf = prediction.get("confidence")
    cat = prediction.get("category", "?")

    if yes_p is None:
        return ""

    lines = [
        f"📊 Signal: {q[:80]}",
        f"Category: {cat}",
        f"Your P: {yes_p:.1%}  Market P: {mkt_p:.1%}  Edge: {edge:+.1%}",
        f"Confidence: {conf:.0%}" if conf else "",
        "",
        "⚠️ UNCALIBRATED — PAPER TRADE ONLY",
        "No resolution history yet. Do not trade on this signal.",
    ]
    return "\n".join(l for l in lines if l)[:MAX_ALERT_LEN]


def compute_alerts(predictions: list, edge_threshold: float,
                   max_alerts: int = 5) -> list:
    """Filter predictions past edge threshold, return formatted alerts.

    predictions: list of prediction dicts with predicted_p + market_p.
    Returns up to max_alerts formatted alert strings, sorted by |edge|.
    """
    candidates = []
    for p in predictions:
        pred_p = p.get("predicted_p")
        mkt_p = p.get("market_p")
        if pred_p is None or mkt_p is None:
            continue
        edge = pred_p - mkt_p
        if abs(edge) > edge_threshold:
            candidates.append((abs(edge), edge, p))
    # Sort by absolute edge descending, take top N
    candidates.sort(key=lambda x: x[0], reverse=True)
    alerts = []
    for _, edge, p in candidates[:max_alerts]:
        alert = format_alert(p, edge)
        if alert:
            alerts.append(alert)
    return alerts


def format_scan_summary(n_markets: int, by_cat: dict, alerts: list,
                       scan_id: int, ts: str) -> str:
    """Format a scan summary for Telegram delivery."""
    lines = [
        f"🔍 Scan #{scan_id} complete ({ts[:16]})",
        f"Markets: {n_markets}",
    ]
    for cat, n in sorted(by_cat.items()):
        lines.append(f"  {cat}: {n}")
    if alerts:
        lines.append(f"\n🚨 {len(alerts)} signal(s):")
        for alert in alerts:
            lines.append(f"\n{alert}")
    else:
        lines.append("\nNo signals this scan.")
    return "\n".join(lines)
