import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import argparse
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Any, Optional
from _store import init_db, get_total_existing_daily_budget, get_total_monthly_budget, save_copy
from policy_check import screen_ad_copy
# NOTE: deploy is lazy-imported inside deploy_campaign() so creator.py stays
# importable without the google-ads lib (needed only for actual deployment).

MAX_DAILY_MULTIPLIER = 2
BATCH_SIZE = 10
# Account monthly spend cap (env override; default $500). Used by guardrail so
# the cap is a real ceiling, not derived from the proposed campaign itself.
ACCOUNT_MONTHLY_CAP = float(os.getenv("MONTHLY_BUDGET", "500"))


def generate_ad_copy(plan: Dict[str, Any], niche: str) -> List[Dict[str, Any]]:
    """Generate 10-15 ad copy variations based on research plan.

    TODO: Integrate with Hermes LLM for copy generation
    """
    print(f"[COPY] Generating ad copy variations for '{niche}'")

    # Placeholder copy generation - would be replaced by Hermes LLM
    variations = []
    keywords = [kw["keyword"] for kw in plan.get("keywords", [])]
    competitors = plan.get("competitors", [])

    # Generate variations with different angles
    angles = [
        "Expert", "Professional", "Local", "Affordable", "Quality",
        "Reliable", "Fast", "Experienced", "Certified", "Trusted"
    ]

    for i in range(12):
        angle = angles[i % len(angles)]
        headlines = [
            f"{angle} {niche.title()} Services",
            f"Best {niche.title()} in {plan['location']}",
            f"{niche.title()} Specialists"
        ]

        descriptions = [
            f"Professional {niche} services in {plan['location']}. Contact us today!",
            f"Local {niche} experts. Quality service at competitive prices."
        ]

        variations.append({
            "headlines": headlines,
            "descriptions": descriptions,
            "path1": niche.replace(" ", "-"),
            "path2": angle.lower()
        })

    print(f"[COPY] Generated {len(variations)} variations")
    return variations


def run_budget_guardrails(db: sqlite3.Connection, daily_budget: float) -> bool:
    """Check account monthly cap. Returns True if within limits.

    Fixes H: the old code added the proposed campaign's monthly spend to the
    total BEFORE computing the cap (total_monthly = existing + daily*30), then
    derived max_daily_total from that inflated figure — so the cap auto-loosened
    to fit ANY proposal and the guardrail never tripped. Now the ceiling is a
    fixed ACCOUNT_MONTHLY_CAP (env MONTHLY_BUDGET) and we compare existing +
    proposed against it (proposed excluded from the cap derivation).
    """
    print(f"[BUDGET] Checking guardrails: daily ${daily_budget:.2f} "
          f"(account cap ${ACCOUNT_MONTHLY_CAP:.0f}/mo)")
    existing_monthly = get_total_monthly_budget(db)        # EXISTING campaigns only
    proposed_monthly = existing_monthly + (daily_budget * 30)
    if proposed_monthly > ACCOUNT_MONTHLY_CAP:
        print(f"⚠️ BUDGET GUARD: account cap exceeded")
        print(f"   Existing ${existing_monthly:.0f}/mo + proposed "
              f"${daily_budget*30:.0f}/mo = ${proposed_monthly:.0f}/mo")
        print(f"   Cap ${ACCOUNT_MONTHLY_CAP:.0f}/mo (MONTHLY_BUDGET env)")
        print(f"   → Reduce daily budget or pause another campaign.")
        return False
    print(f"[BUDGET] OK — projected ${proposed_monthly:.0f}/mo ≤ "
          f"cap ${ACCOUNT_MONTHLY_CAP:.0f}/mo")
    return True


def present_for_approval(variations: List[Dict[str, Any]]) -> List[int]:
    """Present variations for user approval and return selected indices.

    Cron-safe (fixes C-A): if stdin is NOT a tty (Hermes cron, no TTY), this
    prints a clear message and returns [] (→ main exits without deploying, no
    stall, no crash). Also catches EOFError (closed stdin). Full async
    --approve gate is Phase 03 (planned, not yet built).
    """
    if not sys.stdin.isatty():
        print("[APPROVAL] Non-interactive run detected (cron / no TTY).")
        print("[APPROVAL] Approval requires interactive run, OR the async "
              "--approve gate (Phase 03, planned).")
        print("[APPROVAL] Aborting — NO campaign created (safe, no spend).")
        return []

    print("\n" + "="*60)
    print("AD COPY VARIATIONS FOR APPROVAL")
    print("="*60)

    for i, var in enumerate(variations, 1):
        print(f"\n{i}. Headlines:")
        for j, headline in enumerate(var["headlines"], 1):
            print(f"   {j}. {headline}")
        print(f"   Descriptions:")
        for j, desc in enumerate(var["descriptions"], 1):
            print(f"   {j}. {desc}")
        print(f"   Paths: {var['path1']}/{var['path2']}")

    print("\n" + "="*60)
    print("Enter the numbers of variations to approve (comma-separated)")
    print("Example: 1,3,5,8")

    while True:
        try:
            selection = input("> ").strip()
            if not selection:
                print("No selections made. Exiting.")
                return []

            indices = [int(x.strip()) for x in selection.split(",")]
            valid_indices = [i-1 for i in indices if 1 <= i <= len(variations)]

            if not valid_indices:
                print("No valid selections. Try again.")
                continue

            print(f"Selected {len(valid_indices)} variations for deployment.")
            return valid_indices

        except (ValueError, KeyboardInterrupt, EOFError):
            print("Invalid input / EOF. Exiting without deploying.")
            return []


def deploy_campaign(plan: Dict[str, Any], approved_variations: List[Dict[str, Any]],
                   allow_mock: bool = False, customer_id: Optional[str] = None) -> Dict[str, Any]:
    """Deploy approved variations via deploy.deploy_full_campaign (REAL, not stub).

    Initializes a real GoogleAdsClient (or Mock if allow_mock) and runs the full
    deploy pipeline (campaign → ad group → keywords → ads). Returns the deploy
    result dict ({"success": bool, ...}). Fixes C2: previously printed
    "Would deploy" and returned True — a trust violation (reported success with
    nothing deployed). Now actually deploys (or honestly fails / mocks).
    """
    print(f"[DEPLOY] Starting campaign deployment "
          f"({'MOCK' if allow_mock else 'LIVE'} mode)")

    from deploy import get_client, deploy_full_campaign  # lazy: needs google-ads lib
    customer_id = customer_id or os.getenv("GOOGLE_ADS_CUSTOMER_ID")
    if not customer_id:
        if not allow_mock:
            raise RuntimeError(
                "GOOGLE_ADS_CUSTOMER_ID not set. Set it in google-ads.env or use --mock.")
        customer_id = "1234567890"  # mock only

    client = get_client(allow_mock=allow_mock)
    result = deploy_full_campaign(client, customer_id, plan, approved_variations)
    return result  # dict: {success, campaign_resource_name, keywords_created, ads_created, ...}


def main():
    parser = argparse.ArgumentParser(description="Google Ads Campaign Creator")
    parser.add_argument("--plan", type=str, help="Path to research plan JSON file")
    parser.add_argument("--budget", type=int, help="Monthly budget")
    parser.add_argument("--niche", type=str, help="Target niche (for inline research)")
    parser.add_argument("--location", type=str, default="United States", help="Location")
    parser.add_argument("--mock", action="store_true",
                        help="Dry-run with mock Google Ads client (no real deploy, no spend)")

    args = parser.parse_args()

    # Load research plan
    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"Error: Plan file not found: {plan_path}")
            return 1

        with open(plan_path) as f:
            plan = json.load(f)
    else:
        print("Error: Plan file required or inline research not implemented")
        return 1

    # Initialize database
    script_dir = Path(__file__).parent
    db = init_db(script_dir.parent / "data" / "ad-copy-learning.db")

    # Calculate daily budget
    monthly_budget = args.budget or plan.get("monthly_budget", 500)
    daily_budget = round(monthly_budget / 30, 2)

    # Check budget guardrails
    if not run_budget_guardrails(db, daily_budget):
        return 1

    # Generate ad copy variations
    niche = plan.get("niche", args.niche or "target service")
    variations = generate_ad_copy(plan, niche)

    # Screen for policy violations
    print("\n[POLICY] Screening ad copy for policy violations")
    all_passed = True
    for i, var in enumerate(variations):
        result = screen_ad_copy(var["headlines"], var["descriptions"])
        if not result["passed"]:
            print(f"⚠️ Variation {i+1} failed policy check:")
            for violation in result["violations"]:
                print(f"   • {violation}")
            all_passed = False
        else:
            if result["warnings"]:
                print(f"ℹ️ Variation {i+1} has warnings:")
                for warning in result["warnings"]:
                    print(f"   • {warning}")

    if not all_passed:
        print("Policy violations found. Please fix before continuing.")
        return 1

    # Present for approval
    approved_indices = present_for_approval(variations)
    if not approved_indices:
        return 0

    # Get approved variations
    approved_variations = [variations[i] for i in approved_indices]

    # Save to learning database
    campaign_id = f"{niche.replace(' ', '-')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    save_copy(campaign_id, approved_variations, "approved", [])
    save_copy(campaign_id, [v for i, v in enumerate(variations) if i not in approved_indices], "rejected", [])

    # Deploy campaign via deploy.deploy_full_campaign (REAL, or MOCK if --mock)
    try:
        result = deploy_campaign(plan, approved_variations, allow_mock=args.mock)
    except RuntimeError as e:
        print(f"\n❌ Cannot deploy: {e}")
        return 1
    if result.get("success"):
        print(f"\n✅ Campaign deployed: {result.get('campaign_resource_name')}")
        print(f"   Keywords: {result.get('keywords_created', 0)} | "
              f"Ads: {result.get('ads_created', 0)}")
        if args.mock:
            print(f"   ⚠️ MOCK mode — nothing was actually deployed to Google Ads.")
    else:
        print(f"\n❌ Deploy failed: {result.get('error', 'unknown error')}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())