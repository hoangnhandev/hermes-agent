#!/usr/bin/env python3
"""Budget-aware Google Ads strategy generator for Vinfast (Vietnam market).

Replaces the previous mock. Produces HONEST projections (clicks → leads → sales)
from industry benchmarks + recommends model/geo/approach for the given budget.
Deterministic core via _budget_calc; keyword seeds inline for VF-focus.

Usage:
  python3 research.py --budget 10000000 --model vf3 --goal-sales 2
  python3 research.py --budget 5000000 --model vf3           # no goal = projection only

This is the deterministic spine. LLM enhancement (ad-copy angles, keyword
expansion, competitor messaging) is layered by the agent on top of this output.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from _budget_calc import (
    project, budget_tier, assess_goal, model_info, market_cpc,
    recommend_model_for_budget,
    VINFAST_MODELS, VN_AUTOMOTIVE_CPC_USD, VND_PER_USD,
)

# ── Keyword seeds (Vietnam, VF-focused). Full taxonomy in references/. ─────
KEYWORD_SEEDS = {
    "vf3": {
        "branded": ["vinfast vf3", "vf3", "xe vf3", "vinfast vf3 plus"],
        "non_branded": ["xe điện mini", "xe điện giá rẻ", "xe điện vinfast",
                        "xe ô tô điện nhỏ"],
        "intent": ["giá vf3", "đặt lái thử vf3", "mua vf3 trả góp",
                   "vf3 bao nhiêu tiền"],
        "competitor_conquest": ["wuling air", "mini ev", "mg xe điện"],
        "negative": ["vf3 cũ", "phụ tùng vf3", "review vf3", "tin tức vf3",
                     "vf3 second hand", "bán vf3 đã qua sử dụng"],
    },
    # Generic seeds for non-VF3 models (VF3 is the recommended focus)
    "_default": {
        "branded": ["vinfast {m}", "{m}", "xe {m}"],
        "non_branded": ["xe điện suv", "xe điện vinfast", "xe ô tô điện"],
        "intent": ["giá {m}", "đặt lái thử {m}", "mua {m} trả góp"],
        "competitor_conquest": [],
        "negative": ["{m} cũ", "phụ tùng {m}", "review {m}", "tin tức {m}"],
    },
}


def get_keyword_seeds(model_slug: str) -> dict:
    """Return keyword seeds for a model, expanding {m} placeholder for non-VF3."""
    seeds = KEYWORD_SEEDS.get(model_slug, KEYWORD_SEEDS["_default"])
    if model_slug == "vf3":
        return seeds
    return {k: [s.replace("{m}", model_slug) for s in v] for k, v in seeds.items()}


def build_strategy(budget_vnd: int, model_slug: str, market: str,
                   goal_sales: int | None) -> dict:
    """Build full strategy dict: projection + tier + goal + model + keywords."""
    m = model_info(model_slug)
    cpc_usd, cpc_note = market_cpc(market)
    proj = project(budget_vnd, cpc_usd=cpc_usd)
    tier_key, tier_label, tier_note = budget_tier(proj.budget_usd)
    strategy = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "model": {"slug": m.slug, "name": m.name, "price_vnd": m.price_vnd,
                  "segment": m.segment, "competitors": m.competitors,
                  "positioning": m.positioning, "budget_fit": m.budget_fit},
        "budget": {"monthly_vnd": budget_vnd, "monthly_usd": proj.budget_usd,
                   "daily_usd": proj.daily_budget_usd, "daily_vnd": proj.daily_budget_vnd,
                   "tier": tier_key, "tier_label": tier_label, "tier_note": tier_note,
                   "cpc_usd_used": cpc_usd, "cpc_vnd_used": round(cpc_usd * VND_PER_USD),
                   "cpc_source": cpc_note},
        "projection": {
            "clicks_per_month": proj.clicks_per_month,
            "leads_per_month": proj.leads_per_month,
            "sales_per_month": proj.sales_per_month,
            "cpl_usd": proj.cpl_usd, "cpl_vnd": proj.cpl_vnd, "cpa_usd": proj.cpa_usd,
            "months_to_smart_bidding": proj.months_to_smart_bidding,
        },
        "keyword_seeds": get_keyword_seeds(model_slug),
    }
    if goal_sales is not None:
        ga = assess_goal(budget_vnd, goal_sales, cpc_usd=cpc_usd)
        strategy["goal_assessment"] = {
            "goal_sales": ga.goal_sales, "realistic_sales": ga.realistic_sales,
            "achievable": ga.achievable, "budget_needed_vnd": ga.budget_needed_vnd,
            "verdict": ga.verdict,
        }
    return strategy


def print_strategy(s: dict) -> None:
    """Print human-readable honest strategy report."""
    m, b, p = s["model"], s["budget"], s["projection"]
    line = "═" * 60
    print(f"\n{line}\n🎯 GOOGLE ADS STRATEGY — {m['name']} ({s['market'].upper()})\n{line}")
    print(f"📌 Model: {m['name']} — {m['segment']}")
    print(f"   Giá ~{m['price_vnd']:,} VND | Cạnh tranh: {', '.join(m['competitors'])}")
    print(f"   {m['positioning']}")
    print(f"\n💰 Budget: {b['monthly_vnd']:,} VND/tháng "
          f"(~{b['daily_vnd']:,} VND/ngày)")
    print(f"   Tier: {b['tier_label']} — {b['tier_note']}")
    cpc_vnd = b.get('cpc_vnd_used', round(VN_AUTOMOTIVE_CPC_USD * VND_PER_USD))
    cpc_usd = b.get('cpc_usd_used', VN_AUTOMOTIVE_CPC_USD)
    print(f"\n📊 DỰ KIẾN (CPC ~{cpc_vnd:,} VND / ${cpc_usd} — "
          f"{b.get('cpc_source','')}, CVR 7.76%, lead→sale 10%):")
    print(f"   ⚠️ Sales/CPA = UPPER BOUND (CVR & lead→sale là benchmark global;")
    print(f"      thị trường VN thực tế có thể thấp hơn — chưa có data VN-specific).")
    print(f"   • Clicks/tháng:     {p['clicks_per_month']:.0f}")
    print(f"   • Leads (lái thử): {p['leads_per_month']:.1f}")
    print(f"   • Sales (xe):      {p['sales_per_month']:.2f}")
    print(f"   • Cost/lead:       {p['cpl_vnd']:,} VND (~${p['cpl_usd']:.2f})")
    cpa = p['cpa_usd']
    cpa_vnd = round(cpa * VND_PER_USD) if cpa else None
    print(f"   • Cost/sale (CPA): {f'{cpa_vnd:,} VND (~${cpa:,.0f})' if cpa else 'N/A (budget quá thấp)'}")
    sb = p['months_to_smart_bidding']
    print(f"   • Smart bidding sau: {sb} tháng" if sb else
          "   • Smart bidding: KHÔNG reach (budget quá thấp)")
    if "goal_assessment" in s:
        ga = s["goal_assessment"]
        print(f"\n🎯 GOAL CHECK (mục tiêu {ga['goal_sales']} xe/tháng):")
        print(f"   {ga['verdict']}")
    kw = s["keyword_seeds"]
    print(f"\n🔑 KEYWORD SEEDS ({m['slug'].upper()}):")
    print(f"   Branded:     {', '.join(kw['branded'][:4])}")
    print(f"   Non-branded: {', '.join(kw['non_branded'][:4])}")
    print(f"   Intent:      {', '.join(kw['intent'][:4])}")
    if kw["competitor_conquest"]:
        print(f"   Competitor:  {', '.join(kw['competitor_conquest'][:3])}")
    print(f"   Negative:    {', '.join(kw['negative'][:4])}")
    print(f"\n💡 MODEL FIT: {m['budget_fit']}")
    print(f"📖 Full taxonomy/benchmarks: references/automotive-keyword-taxonomy.md, "
          f"automotive-benchmarks.md")
    print(f"{line}\n")


def save_strategy(s: dict, data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d")
    fp = data_dir / f"strategy-{s['model']['slug']}-{ts}.json"
    fp.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    return fp


def main() -> None:
    ap = argparse.ArgumentParser(description="Vinfast Google Ads budget-aware strategy generator")
    ap.add_argument("--budget", type=int, required=True,
                    help="Monthly budget in VND (e.g. 10000000 = 10 triệu)")
    ap.add_argument("--model", default=None, choices=list(VINFAST_MODELS),
                    help="Vinfast model (default: auto-pick optimal by budget)")
    ap.add_argument("--market", default="vn", help="Market code (default: vn)")
    ap.add_argument("--goal-sales", type=int, default=None,
                    help="Target vehicle sales/month for honest goal check")
    ap.add_argument("--json", action="store_true", help="Output JSON only (for agent)")
    args = ap.parse_args()

    # Auto-pick the optimal model for the budget when --model is omitted.
    # Highest viable model (see recommend_model_for_budget): low budget → VF3,
    # scales up to pricier higher-margin models as budget allows.
    model = args.model
    if model is None:
        model, reason = recommend_model_for_budget(args.budget)
        if not args.json:
            print(f"🤖 Model tự chọn theo budget: {reason}\n")

    strategy = build_strategy(args.budget, model, args.market, args.goal_sales)
    if args.json:
        print(json.dumps(strategy, indent=2, ensure_ascii=False))
        return
    print_strategy(strategy)
    fp = save_strategy(strategy, Path(__file__).parent.parent / "data")
    print(f"💾 Saved: {fp}")


if __name__ == "__main__":
    main()
