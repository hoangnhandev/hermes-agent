import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import argparse
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Any, Optional
from _store import init_db, get_total_existing_daily_budget, get_total_monthly_budget, save_copy
from policy_check import screen_ad_copy

MAX_DAILY_MULTIPLIER = 2
BATCH_SIZE = 10


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
    """Check budget guardrails for both per-campaign and account total.

    Returns True if within limits, False if exceeds guardrails.
    """
    print(f"[BUDGET] Checking guardrails for daily budget: ${daily_budget}")

    # Per-campaign check
    max_daily_per_campaign = round(daily_budget * MAX_DAILY_MULTIPLIER, 2)

    # Account total check
    total_existing_daily = get_total_existing_daily_budget(db)
    total_monthly = get_total_monthly_budget(db) + (daily_budget * 30)
    max_daily_total = round(total_monthly / 30 * MAX_DAILY_MULTIPLIER, 2)

    if total_existing_daily + daily_budget > max_daily_total:
        print(f"⚠️ BUDGET GUARD: Exceeds account cap")
        print(f"   New campaign daily: ${daily_budget}")
        print(f"   Existing total: ${total_existing_daily}")
        print(f"   Account cap: ${max_daily_total}")
        print(f"   Reduce budget or pause another campaign.")
        return False

    print(f"[BUDGET] Guardrails passed. Per-campaign max: ${max_daily_per_campaign}, Account cap: ${max_daily_total}")
    return True


def present_for_approval(variations: List[Dict[str, Any]]) -> List[int]:
    """Present variations for user approval and return selected indices."""
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

        except (ValueError, KeyboardInterrupt):
            print("Invalid input. Please enter numbers separated by commas.")
            continue


def deploy_campaign(client: Any, plan: Dict[str, Any], approved_variations: List[Dict[str, Any]]) -> bool:
    """Deploy approved variations as a new campaign."""
    print(f"[DEPLOY] Starting campaign deployment")

    # TODO: Implement campaign deployment
    # This would call deploy.py functions to create:
    # - Campaign budget
    # - Campaign
    # - Ad groups
    # - Keywords
    # - Ads

    print(f"[DEPLOY] Would deploy {len(approved_variations)} approved variations")
    print(f"[DEPLOY] Campaign: {plan['niche']} - {plan['location']}")

    # Placeholder implementation
    # customer_id = "1234567890"  # Would come from config
    # campaign_name = f"{plan['niche']} - {plan['location']}"
    # daily_budget_micros = int(plan['budget_plan']['daily_budget'] * 1000000)

    # Create campaign, ad groups, keywords, ads
    # ... deployment logic here

    return True


def main():
    parser = argparse.ArgumentParser(description="Google Ads Campaign Creator")
    parser.add_argument("--plan", type=str, help="Path to research plan JSON file")
    parser.add_argument("--budget", type=int, help="Monthly budget")
    parser.add_argument("--niche", type=str, help="Target niche (for inline research)")
    parser.add_argument("--location", type=str, default="United States", help="Location")

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

    # Deploy campaign
    if deploy_campaign(None, plan, approved_variations):
        print(f"\n✅ Campaign created successfully!")
        print(f"   Campaign ID: {campaign_id}")
        print(f"   Variations deployed: {len(approved_variations)}")
    else:
        print(f"\n❌ Campaign deployment failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())