#!/usr/bin/env python3
"""Deterministic budget projections + Vinfast model data for google-ads skill.

No LLM, no network. Pure math from industry benchmarks (WordStream/LocaliQ 2025,
automotive sector) so projections are testable + reproducible. LLM enhancement
(keyword expansion, ad angles) lives in research.py orchestrator on top of this.

Funnel: budget → clicks → leads (test-drive bookings) → sales.
Rates are industry averages; real results vary by model/geo/copy/landing page.
"""
from __future__ import annotations
from dataclasses import dataclass, field

# ── Industry benchmarks (automotive, WordStream/LocaliQ 2025) ──────────────
AUTOMOTIVE_CPC_USD = 2.41      # avg cost-per-click (54% lower than general $5.26)
AUTOMOTIVE_CVR = 0.0776        # click → lead (test-drive booking) conversion
TESTDRIVE_TO_SALE = 0.10       # lead (test-drive) → vehicle sale close rate
# (industry test-drive close rate ~5-20%; 10% is a conservative mid estimate)

VND_PER_USD = 25_000           # approx FX for VND ↔ USD display

# ── Budget tiers (USD/month) + smart-bidding threshold ─────────────────────
SMART_BIDDING_MIN_CONVERSIONS = 30  # tCPA/tROAS needs 30 conversions/30d

TIERS = [
    # (max_usd, key, label, note)
    (500, "testing", "Testing only",
     "Quá thấp để tối ưu. Chỉ thu data. ~6-7 clicks/ngày. Không reach smart bidding (2+ tháng)."),
    (1500, "min_viable", "Minimum viable",
     "Đủ đo lường: 1 thành phố, 1-2 model. 20-40 clicks/ngày. Smart bidding 1-2 tháng."),
    (3000, "recommended", "Recommended",
     "Đa model, national VN. 40-110 clicks/ngày. Smart bidding 2-4 tuần."),
    (8000, "aggressive", "Aggressive growth",
     "Performance Max Vehicle Ads + competitor conquest. 110+ clicks/ngày."),
    (float("inf"), "enterprise", "Enterprise",
     "Full funnel, multi-region. Reserved cho dealer lớn / brand campaign."),
]


# ── Vinfast models (Vietnam market, approx VND retail, 2024-2025) ──────────
# price_vnd: approx mid retail (battery-included). segment: market positioning.
@dataclass
class ModelInfo:
    slug: str
    name: str
    price_vnd: int
    segment: str
    competitors: list = field(default_factory=list)
    positioning: str = ""
    budget_fit: str = ""  # note on fit for low budget

VINFAST_MODELS: dict[str, ModelInfo] = {
    "vf3": ModelInfo(
        "vf3", "Vinfast VF3", 280_000_000, "Mini EV (2-door)",
        competitors=["Wuling Air", "Mini EV", "MG"],
        positioning="Xe điện giá rẻ nhất thị trường, ngõ hẻm đô thị, first-car/second-car.",
        budget_fit="BEST cho budget thấp: giá thấp → CVR cao nhất → volume sale. Recommend."),
    "vf5": ModelInfo(
        "vf5", "Vinfast VF5 Plus", 520_000_000, "A0 SUV điện",
        competitors=["Hyundai Casper", "Toyota Raize", "Kia Sonet"],
        positioning="SUV đô thị cỡ nhỏ, gia đình trẻ, sweet spot giá.",
        budget_fit="Tốt — sweet spot giá, CVR khá. Phù hợp nếu khách nhắm phân khúc lớn hơn VF3."),
    "vf6": ModelInfo(
        "vf6", "Vinfast VF6", 620_000_000, "Asegment SUV điện",
        competitors=["Hyundai Creta", "Mitsubishi Xforce", "Kia Seltos"],
        positioning="SUV cỡ nhỏ gọn, rộng hơn VF5, cho gia đình.",
        budget_fit="Khá — cần budget cao hơn ($400+/mo) để CVR đủ."),
    "vf7": ModelInfo(
        "vf7", "Vinfast VF7", 950_000_000, "C-segment SUV điện",
        competitors=["Hyundai Tucson", "Ford Territory", "MG GS"],
        positioning="SUV cỡ trung, thiết kế thể thao, phân khúc premium-mid.",
        budget_fit="Khó — khách premium, cân nhắc dài, CVR thấp. Cần $1,000+/mo."),
    "vf8": ModelInfo(
        "vf8", "Vinfast VF8", 1_300_000_000, "D-segment SUV điện",
        competitors=["Ford Everest", "Hyundai SantaFe", "Toyota Fortuner"],
        positioning="SUV cỡ lớn premium, gia đình nhiều thế hệ.",
        budget_fit="Khó — high-ticket, cần budget lớn + nurturing dài."),
    "vf9": ModelInfo(
        "vf9", "Vinfast VF9", 1_700_000_000, "E-segment SUV điện (flagship)",
        competitors=["Lexus RX", "Mercedes GLE", "BMW X5"],
        positioning="Flagship SUV full-size, cao cấp nhất dòng VF.",
        budget_fit="Rất khó — ultra-premium. Brand campaign, không performance lead với budget thấp."),
}


@dataclass
class Projection:
    budget_vnd: int
    budget_usd: float
    daily_budget_usd: float
    clicks_per_month: float
    leads_per_month: float        # test-drive bookings
    sales_per_month: float        # estimated vehicle sales
    cpl_usd: float                # cost per lead
    cpa_usd: float                # cost per acquisition (sale)
    months_to_smart_bidding: float


def project(budget_vnd: int, cpc_usd: float = AUTOMOTIVE_CPC_USD,
            cvr: float = AUTOMOTIVE_CVR,
            lead_to_sale: float = TESTDRIVE_TO_SALE) -> Projection:
    """Project funnel metrics from monthly budget (VND)."""
    budget_usd = budget_vnd / VND_PER_USD
    daily_usd = budget_usd / 30
    clicks = budget_usd / cpc_usd                 # total clicks/month
    leads = clicks * cvr                          # test-drive bookings
    sales = leads * lead_to_sale                  # vehicle sales
    cpl = budget_usd / leads if leads > 0 else 0.0
    cpa = budget_usd / sales if sales > 0 else float("inf")
    months_to_sb = SMART_BIDDING_MIN_CONVERSIONS / leads if leads > 0 else float("inf")
    return Projection(
        budget_vnd=budget_vnd, budget_usd=round(budget_usd, 2),
        daily_budget_usd=round(daily_usd, 2),
        clicks_per_month=round(clicks, 1),
        leads_per_month=round(leads, 1),
        sales_per_month=round(sales, 2),
        cpl_usd=round(cpl, 2), cpa_usd=round(cpa, 2) if cpa != float("inf") else None,
        months_to_smart_bidding=round(months_to_sb, 1) if months_to_sb != float("inf") else None,
    )


def budget_tier(budget_usd: float) -> tuple[str, str, str]:
    """Return (key, label, note) for budget tier."""
    for max_usd, key, label, note in TIERS:
        if budget_usd <= max_usd:
            return key, label, note
    return TIERS[-1][1], TIERS[-1][2], TIERS[-1][3]


@dataclass
class GoalAssessment:
    goal_sales: int
    realistic_sales: float          # what budget actually projects
    achievable: bool
    budget_needed_vnd: int          # budget to hit goal_sales
    verdict: str


def assess_goal(budget_vnd: int, goal_sales: int,
                cpc_usd: float = AUTOMOTIVE_CPC_USD,
                cvr: float = AUTOMOTIVE_CVR,
                lead_to_sale: float = TESTDRIVE_TO_SALE) -> GoalAssessment:
    """Assess if budget can realistically hit goal_sales/month. Honest."""
    proj = project(budget_vnd, cpc_usd, cvr, lead_to_sale)
    achievable = proj.sales_per_month >= goal_sales
    # Reverse-funnel: goal_sales → leads needed → clicks → budget
    leads_needed = goal_sales / lead_to_sale
    clicks_needed = leads_needed / cvr
    budget_needed_usd = clicks_needed * cpc_usd
    budget_needed_vnd = int(round(budget_needed_usd * VND_PER_USD / 1_000_000) * 1_000_000)
    if achievable:
        verdict = (f"✅ ĐẠT — budget {budget_vnd:,} VND dự kiến "
                   f"{proj.sales_per_month} xe/tháng (goal {goal_sales}).")
    else:
        verdict = (f"⚠️ KHÔNG ĐẠT — budget {budget_vnd:,} VND dự kiến chỉ "
                   f"{proj.sales_per_month} xe/tháng (goal {goal_sales}). "
                   f"Cần ~{budget_needed_vnd:,} VND/tháng ({budget_needed_usd:,.0f} USD) "
                   f"để đạt {goal_sales} xe.")
    return GoalAssessment(
        goal_sales=goal_sales, realistic_sales=proj.sales_per_month,
        achievable=achievable, budget_needed_vnd=budget_needed_vnd, verdict=verdict,
    )


def model_info(slug: str) -> ModelInfo:
    """Return ModelInfo for a Vinfast model slug (case-insensitive)."""
    s = slug.lower().strip()
    if s not in VINFAST_MODELS:
        raise KeyError(f"Unknown model '{slug}'. Valid: {list(VINFAST_MODELS)}")
    return VINFAST_MODELS[s]
