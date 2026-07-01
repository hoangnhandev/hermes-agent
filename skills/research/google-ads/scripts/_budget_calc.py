#!/usr/bin/env python3
"""Deterministic budget projections + Vinfast model data for google-ads skill.

No LLM, no network. Pure math from industry benchmarks (WordStream/LocaliQ 2025,
automotive sector) so projections are testable + reproducible. LLM enhancement
(keyword expansion, ad angles) lives in research.py orchestrator on top of this.

Funnel: budget → clicks → leads (test-drive bookings) → sales.
Rates are industry averages; real results vary by model/geo/copy/landing page.
"""
from __future__ import annotations
import math
import os
from dataclasses import dataclass, field

# ── Industry benchmarks (automotive) ───────────────────────────────────────
# CPC differs sharply by market. VN CPC is ~76% below US (leadsoff 2025:
# VN all-industry avg $0.35-0.60 vs WordStream global $5.26). Automotive is
# medium-high competition in VN, so we use the upper-mid of the VN range.
# NB: CVR/lead-to-sale below remain US/global benchmarks (VN-specific CVR
# data is scarce); real VN CVR may be lower → treat sales as upper bound.
AUTOMOTIVE_CPC_USD = 2.41      # US/global avg (WordStream/LocaliQ 2025 automotive)
VN_AUTOMOTIVE_CPC_USD = 0.50   # VN automotive est (range $0.30-0.80: branded cheap, intent pricey)
MARKET_CPC = {"vn": VN_AUTOMOTIVE_CPC_USD, "global": AUTOMOTIVE_CPC_USD}
AUTOMOTIVE_CVR = 0.0776        # click → lead (test-drive booking) conversion
TESTDRIVE_TO_SALE = 0.10       # lead (test-drive) → vehicle sale close rate
# (industry test-drive close rate ~5-20%; 10% is a conservative mid estimate)

VND_PER_USD = 25_000           # approx FX for VND ↔ USD display

# VND equivalents of the USD benchmarks (= _USD × VND_PER_USD). VND is the
# skill's display + comparison currency everywhere a user sees a number; the
# _USD originals stay as the source-of-truth benchmarks (WordStream/LocaliQ).
AUTOMOTIVE_CPC_VND = round(AUTOMOTIVE_CPC_USD * VND_PER_USD)        # ~60,250
VN_AUTOMOTIVE_CPC_VND = round(VN_AUTOMOTIVE_CPC_USD * VND_PER_USD)  # ~12,500
MARKET_CPC_VND = {"vn": VN_AUTOMOTIVE_CPC_VND, "global": AUTOMOTIVE_CPC_VND}


# ── Currency conversion (VND ↔ Google Ads API micros) ───────────────────────
def account_currency() -> str:
    """Google Ads account billing currency (env override). Default VND.

    Why: API amount_micros are denominated in the account currency. A VN
    account bills in VND (default). Set ACCOUNT_CURRENCY=USD only if the real
    account bills in USD — the helpers below then convert VND↔USD at the API
    boundary so the rest of the pipeline stays in VND.
    """
    return os.getenv("ACCOUNT_CURRENCY", "VND").strip().upper()


def to_micros_from_vnd(vnd: float) -> int:
    """VND amount → Google Ads API micros, honoring ACCOUNT_CURRENCY.

    VND account: micros = vnd × 1e6 (1 micro = 1e-6 of the account unit).
    USD account: convert vnd→USD first (vnd / VND_PER_USD), then × 1e6.
    """
    acct = vnd if account_currency() != "USD" else vnd / VND_PER_USD
    return int(round(acct * 1_000_000))


def from_micros(micros: int) -> float:
    """Google Ads API micros → VND (display currency).

    API micros are in the account currency; a USD account's micros are scaled
    to USD so multiply by VND_PER_USD to return VND for display.
    """
    acct = micros / 1_000_000.0
    return acct * VND_PER_USD if account_currency() == "USD" else acct


def fmt_vnd(amount) -> str:
    """Format a VND amount for display: '12.500.000₫' (vi-VN grouping, no
    decimals — VND has no subdivision). None/NaN → '0₫'."""
    try:
        n = int(round(float(amount or 0)))
    except (TypeError, ValueError):
        n = 0
    return f"{n:,}₫".replace(",", ".")


def market_cpc(market: str) -> tuple[float, str]:
    """Return (cpc_usd, source_note) for a market code. Defaults to VN.

    Why: $2.41 is the US/global automotive CPC; using it for VN overstates
    cost ~5x and makes projections needlessly pessimistic. VN default keeps
    the skill honest for its Vinfast-VN focus.
    """
    m = (market or "vn").strip().lower()
    if m in ("vn", "vietnam", "viet nam"):
        return (VN_AUTOMOTIVE_CPC_USD,
                f"VN automotive est ${VN_AUTOMOTIVE_CPC_USD} (range $0.30-0.80)")
    return (AUTOMOTIVE_CPC_USD,
            f"US/global automotive ${AUTOMOTIVE_CPC_USD} (WordStream 2025)")

# ── Budget tiers (USD/month) + smart-bidding threshold ─────────────────────
SMART_BIDDING_MIN_CONVERSIONS = 30  # tCPA/tROAS needs 30 conversions/30d.
# "Conversion" here = lead (test-drive booking), the tracked primary
# conversion; months_to_smart_bidding = 30 / leads_per_month.

TIERS = [
    # (max_usd, key, label, note) — qualitative only. Exact clicks + time-to-
    # smart-bidding come from the projection (they depend on market CPC, so we
    # don't hardcode them here — hardcoding drifts as CPC changes by market).
    (500, "testing", "Testing only",
     "Quá thấp để tối ưu. Chỉ thu data, 1-2 từ khóa. (Xem months_to_smart_bidding ở projection.)"),
    (1500, "min_viable", "Minimum viable",
     "Đủ đo lường: 1 thành phố, 1-2 model."),
    (3000, "recommended", "Recommended",
     "Đa model, national VN."),
    (8000, "aggressive", "Aggressive growth",
     "Performance Max Vehicle Ads + competitor conquest."),
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
    daily_budget_vnd: int         # daily in VND (display currency)
    clicks_per_month: float
    leads_per_month: float        # test-drive bookings
    sales_per_month: float        # estimated vehicle sales
    cpl_usd: float                # cost per lead (USD benchmark)
    cpl_vnd: int                  # cost per lead in VND (display)
    cpa_usd: float | None         # cost per acquisition (sale); None if sales==0
    months_to_smart_bidding: float | None  # None if leads==0 (never reaches threshold)


def project(budget_vnd: int, cpc_usd: float = AUTOMOTIVE_CPC_USD,
            cvr: float = AUTOMOTIVE_CVR,
            lead_to_sale: float = TESTDRIVE_TO_SALE) -> Projection:
    """Project funnel metrics from monthly budget (VND).

    Inputs validated: bad values (negative budget, zero CPC/CVR/close-rate)
    raise ValueError rather than emitting misleading negatives or div-by-zero.
    cpa_usd/months_to_smart_bidding are None when sales/leads are 0 (e.g.
    budget_vnd==0) — JSON consumers must handle null (they are typed Optional).
    """
    if budget_vnd < 0:
        raise ValueError(f"budget_vnd must be >= 0, got {budget_vnd}")
    if cpc_usd <= 0:
        raise ValueError(f"cpc_usd must be > 0, got {cpc_usd}")
    if not 0 < cvr <= 1:
        raise ValueError(f"cvr must be in (0, 1], got {cvr}")
    if not 0 < lead_to_sale <= 1:
        raise ValueError(f"lead_to_sale must be in (0, 1], got {lead_to_sale}")
    budget_usd = budget_vnd / VND_PER_USD
    daily_usd = budget_usd / 30
    daily_vnd = round(budget_vnd / 30) if budget_vnd > 0 else 0
    clicks = budget_usd / cpc_usd                 # total clicks/month
    leads = clicks * cvr                          # test-drive bookings
    sales = leads * lead_to_sale                  # vehicle sales
    cpl = budget_usd / leads if leads > 0 else 0.0
    cpl_vnd_val = round(budget_vnd / leads) if leads > 0 else 0
    cpa = budget_usd / sales if sales > 0 else float("inf")
    months_to_sb = SMART_BIDDING_MIN_CONVERSIONS / leads if leads > 0 else float("inf")
    return Projection(
        budget_vnd=budget_vnd, budget_usd=round(budget_usd, 2),
        daily_budget_usd=round(daily_usd, 2),
        daily_budget_vnd=daily_vnd,
        clicks_per_month=round(clicks, 1),
        leads_per_month=round(leads, 1),
        sales_per_month=round(sales, 2),
        cpl_usd=round(cpl, 2), cpl_vnd=cpl_vnd_val,
        cpa_usd=round(cpa, 2) if cpa != float("inf") else None,
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
    if goal_sales < 1:
        raise ValueError(f"goal_sales must be >= 1, got {goal_sales}")
    proj = project(budget_vnd, cpc_usd, cvr, lead_to_sale)
    achievable = proj.sales_per_month >= goal_sales
    # Reverse-funnel: goal_sales → leads needed → clicks → budget.
    # Round UP (ceil) so the recommended budget always suffices — round() to
    # nearest million can under-deliver the goal the verdict promises.
    leads_needed = goal_sales / lead_to_sale
    clicks_needed = leads_needed / cvr
    budget_needed_usd = clicks_needed * cpc_usd
    budget_needed_vnd = int(math.ceil(budget_needed_usd * VND_PER_USD / 1_000_000) * 1_000_000)
    if achievable:
        verdict = (f"✅ ĐẠT — budget {budget_vnd:,} VND dự kiến "
                   f"~{proj.sales_per_month} xe/tháng (goal {goal_sales}). "
                   f"(UPPER BOUND — CVR/lead→sale là benchmark global, VN thực tế có thể thấp hơn.)")
    else:
        verdict = (f"⚠️ KHÔNG ĐẠT — budget {budget_vnd:,} VND dự kiến chỉ "
                   f"~{proj.sales_per_month} xe/tháng (goal {goal_sales}). "
                   f"Cần ~{budget_needed_vnd:,} VND/tháng ({budget_needed_usd:,.0f} USD) "
                   f"để đạt {goal_sales} xe. "
                   f"(UPPER BOUND — CVR/lead→sale là benchmark global.)")
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
