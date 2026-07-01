#!/usr/bin/env python3
"""Monthly optimization analysis loop for google-ads skill.

Analyzes historical daily_metrics (collected by monitor.py) for a period,
compares to the previous period (baseline), identifies winners/losers, and
generates an actionable optimization plan for the NEXT period.

Philosophy: same track → analyze → improve loop as polymarket-signals
calibration. Each run: period summary vs baseline, top/worst performers,
wasted spend, concrete actions (scale/pause/rebid/add negatives).

Usage:
  python3 optimize.py                       # last 30d vs previous 30d
  python3 optimize.py --days 30 --entity keyword
  python3 optimize.py --json                # machine-readable for agent
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from _budget_calc import fmt_vnd

DB_PATH = Path(__file__).parent.parent / "data" / "campaigns-local.db"

# Action thresholds in VND (display currency). USD source: WASTED=$5, CPA=$200.
WASTED_SPEND_VND = 125_000     # cost ≥ this with 0 conv → pause candidate ($5)
SCALE_MIN_CONVERSIONS = 2      # conversions ≥ this → consider scaling
CPA_GOOD_VND = 5_000_000       # CPA below this for a VF3 (~280M VND) → profitable ($200)
CVR_DROP_PCT = 20.0            # CVR dropped >20% vs baseline → watch


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_optimization_log(conn)
    return conn


def _ensure_optimization_log(conn: sqlite3.Connection) -> None:
    """Create optimization_log if missing (tracks actions + later impact)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS optimization_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            entity_type TEXT,
            entity_id TEXT,
            action TEXT NOT NULL,
            reason TEXT,
            metric_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def _period_bounds(days: int) -> tuple[date, date, date, date]:
    """Return (cur_start, cur_end, base_start, base_end) for current + baseline."""
    cur_end = date.today() - timedelta(days=1)          # yesterday (complete days)
    cur_start = cur_end - timedelta(days=days - 1)
    base_end = cur_start - timedelta(days=1)
    base_start = base_end - timedelta(days=days - 1)
    return cur_start, cur_end, base_start, base_end


def _agg(conn: sqlite3.Connection, entity_type: str, start: date, end: date) -> dict:
    """Aggregate metrics for an entity_type over [start, end]."""
    row = conn.execute("""
        SELECT COALESCE(SUM(impressions),0) impressions,
               COALESCE(SUM(clicks),0) clicks,
               COALESCE(SUM(cost),0) cost,
               COALESCE(SUM(conversions),0) conversions,
               COALESCE(SUM(conversion_value),0) conversion_value
        FROM daily_metrics WHERE entity_type=? AND date>=? AND date<=?
    """, (entity_type, start.isoformat(), end.isoformat())).fetchone()
    imp, clk, cost, conv, val = (row["impressions"], row["clicks"],
                                 row["cost"], row["conversions"], row["conversion_value"])
    ctr = clk / imp if imp else 0.0
    cvr = conv / clk if clk else 0.0
    cpc = cost / clk if clk else 0.0
    cpa = cost / conv if conv else None
    roas = val / cost if cost else 0.0
    return {"impressions": imp, "clicks": clk, "cost": round(cost, 2),
            "conversions": conv, "conversion_value": round(val, 2),
            "ctr": round(ctr, 4), "cvr": round(cvr, 4),
            "cpc": round(cpc, 2), "cpa": round(cpa, 2) if cpa else None,
            "roas": round(roas, 2)}


def _top_performers(conn: sqlite3.Connection, entity_type: str,
                    start: date, end: date, limit: int = 5) -> list:
    """Top entities by conversions (winners)."""
    rows = conn.execute("""
        SELECT entity_id, SUM(impressions) impressions, SUM(clicks) clicks,
               SUM(cost) cost, SUM(conversions) conversions
        FROM daily_metrics WHERE entity_type=? AND date>=? AND date<=?
        GROUP BY entity_id HAVING SUM(conversions) > 0
        ORDER BY SUM(conversions) DESC, (CASE WHEN SUM(cost)>0 THEN SUM(conversions)*1.0/SUM(cost) ELSE 0 END) DESC
        LIMIT ?
    """, (entity_type, start.isoformat(), end.isoformat(), limit)).fetchall()
    return [_entity_dict(r) for r in rows]


def _wasted_spend(conn: sqlite3.Connection, entity_type: str,
                  start: date, end: date) -> list:
    """Entities with cost >= threshold but 0 conversions (losers)."""
    rows = conn.execute("""
        SELECT entity_id, SUM(impressions) impressions, SUM(clicks) clicks,
               SUM(cost) cost, SUM(conversions) conversions
        FROM daily_metrics WHERE entity_type=? AND date>=? AND date<=?
        GROUP BY entity_id HAVING SUM(cost) >= ? AND SUM(conversions) = 0
        ORDER BY SUM(cost) DESC
    """, (entity_type, start.isoformat(), end.isoformat(), WASTED_SPEND_VND)).fetchall()
    return [_entity_dict(r) for r in rows]


def _entity_dict(r: sqlite3.Row) -> dict:
    cost, conv = r["cost"], r["conversions"]
    return {"entity_id": r["entity_id"], "impressions": r["impressions"],
            "clicks": r["clicks"], "cost": round(cost, 2), "conversions": conv,
            "cvr": round(conv / r["clicks"], 4) if r["clicks"] else 0.0,
            "cpa": round(cost / conv, 2) if conv else None}


def _recommend(cur: dict, base: dict | None, top: list, wasted: list) -> list:
    """Generate actionable optimization recommendations (the plan)."""
    actions = []
    # Scale winners
    for e in top:
        if e["conversions"] >= SCALE_MIN_CONVERSIONS and (
                e["cpa"] is None or e["cpa"] <= CPA_GOOD_VND):
            actions.append({"action": "SCALE", "entity": e["entity_id"],
                            "reason": f"{e['conversions']} conv, CPA {fmt_vnd(e['cpa'])} — tăng bid/budget"})
    # Pause wasted spend
    for e in wasted:
        actions.append({"action": "PAUSE", "entity": e["entity_id"],
                        "reason": f"{fmt_vnd(e['cost'])} chi, 0 conv — pause hoặc negative"})
    # CVR trend watch
    if base and cur["clicks"] > 50 and base["cvr"] > 0:
        drop = (base["cvr"] - cur["cvr"]) / base["cvr"] * 100
        if drop >= CVR_DROP_PCT:
            actions.append({"action": "WATCH_CVR_DROP", "entity": "*",
                            "reason": f"CVR giảm {drop:.0f}% vs baseline "
                                      f"({cur['cvr']*100:.1f}% ← {base['cvr']*100:.1f}%) — "
                                      f"kiểm tra landing page/ad copy/negative kw"})
    if not actions:
        actions.append({"action": "HOLD", "entity": "*",
                        "reason": "Không đủ signal mạnh — tiếp tục thu data, "
                                  "tối ưu landing page trước khi rebid."})
    return actions


def analyze(days: int = 30, entity_type: str = "keyword") -> dict:
    """Full optimization analysis: current vs baseline + recommendations."""
    conn = _conn()
    cs, ce, bs, be = _period_bounds(days)
    cur = _agg(conn, entity_type, cs, ce)
    base = _agg(conn, entity_type, bs, be) if _has_data(conn, entity_type, bs, be) else None
    top = _top_performers(conn, entity_type, cs, ce)
    wasted = _wasted_spend(conn, entity_type, cs, ce)
    actions = _recommend(cur, base, top, wasted)
    # Period-over-period deltas
    deltas = _deltas(cur, base)
    result = {
        "run_date": date.today().isoformat(),
        "entity_type": entity_type,
        "current_period": {"start": cs.isoformat(), "end": ce.isoformat(), **cur},
        "baseline_period": ({"start": bs.isoformat(), "end": be.isoformat(), **base}
                            if base else None),
        "period_deltas": deltas,
        "top_performers": top,
        "wasted_spend": wasted,
        "recommendations": actions,
    }
    conn.close()
    return result


def _has_data(conn, entity_type, start, end) -> bool:
    r = conn.execute("SELECT COUNT(*) c FROM daily_metrics WHERE entity_type=? AND date>=? AND date<=?",
                     (entity_type, start.isoformat(), end.isoformat())).fetchone()
    return r["c"] > 0


def _deltas(cur: dict, base: dict | None) -> dict:
    if not base:
        return {"note": "không có baseline (lần chạy đầu)"}
    def pct(c, b):
        return round((c - b) / b * 100, 1) if b else None
    return {"clicks_pct": pct(cur["clicks"], base["clicks"]),
            "cost_pct": pct(cur["cost"], base["cost"]),
            "conversions_pct": pct(cur["conversions"], base["conversions"]),
            "cpa_pct": pct(cur["cpa"] or 0, base["cpa"] or 0),
            "cvr_pct": pct(cur["cvr"], base["cvr"])}


def _log_actions(result: dict) -> None:
    """Persist recommendations to optimization_log (for impact tracking next run)."""
    conn = _conn()
    cs = result["current_period"]["start"]
    ce = result["current_period"]["end"]
    for a in result["recommendations"]:
        conn.execute("""INSERT INTO optimization_log
            (run_date, period_start, period_end, entity_type, entity_id, action, reason)
            VALUES (?,?,?,?,?,?,?)""",
            (result["run_date"], cs, ce, result["entity_type"],
             a["entity"], a["action"], a["reason"]))
    conn.commit()
    conn.close()


def print_report(r: dict) -> None:
    cp, bp = r["current_period"], r["baseline_period"]
    d = r["period_deltas"]
    line = "═" * 60
    print(f"\n{line}\n📈 OPTIMIZATION REVIEW — {r['entity_type'].upper()} "
          f"({cp['start']} → {cp['end']})\n{line}")
    print(f"\n📊 HIỆU SUẤT KỲ NÀY:")
    print(f"   Clicks {cp['clicks']} | Cost {fmt_vnd(cp['cost'])} | Conv {cp['conversions']} | "
          f"CVR {cp['cvr']*100:.1f}% | CPA {fmt_vnd(cp['cpa']) if cp['cpa'] else 'N/A'}")
    if bp:
        print(f"\n📅 VS BASELINE ({bp['start']} → {bp['end']}):")
        if isinstance(d, dict) and "clicks_pct" in d:
            print(f"   Clicks {d['clicks_pct']:+.0f}% | Cost {d['cost_pct']:+.0f}% | "
                  f"Conv {d['conversions_pct']:+.0f}% | CVR {d['cvr_pct']:+.0f}%")
    else:
        print(f"\n📅 {d.get('note', '(no baseline)')}")
    print(f"\n🏆 TOP PERFORMERS (scale lên):")
    for e in r["top_performers"][:5]:
        print(f"   • {e['entity_id']}: {e['conversions']} conv, "
              f"{fmt_vnd(e['cost'])} cost, CPA {fmt_vnd(e['cpa']) if e['cpa'] else '-'}")
    if r["wasted_spend"]:
        print(f"\n🗑️ WASTED SPEND (pause/negative):")
        for e in r["wasted_spend"][:5]:
            print(f"   • {e['entity_id']}: {fmt_vnd(e['cost'])} chi, 0 conv")
    print(f"\n🎯 KẾ HOẠCH TỐI ƯU THÁNG SAU:")
    for a in r["recommendations"]:
        print(f"   [{a['action']}] {a['entity']} — {a['reason']}")
    print(f"{line}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Monthly optimization analysis loop")
    ap.add_argument("--days", type=int, default=30, help="Current period length (default 30)")
    ap.add_argument("--entity", default="keyword", choices=["keyword", "ad_group", "campaign"])
    ap.add_argument("--json", action="store_true", help="JSON output for agent")
    args = ap.parse_args()
    if not DB_PATH.exists():
        print(f"❌ Chưa có data ({DB_PATH}). Chạy monitor.py trước để thu metrics.")
        return
    result = analyze(args.days, args.entity)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)
    _log_actions(result)


if __name__ == "__main__":
    main()
