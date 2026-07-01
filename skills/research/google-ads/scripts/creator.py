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
from _store import init_db, get_total_existing_daily_budget, get_total_monthly_budget, save_copy, save_campaign
from policy_check import screen_ad_copy
from approval_gate import write_pending, read_pending, mark_status, approval_lock
# NOTE: deploy is lazy-imported inside deploy_campaign() so creator.py stays
# importable without the google-ads lib (needed only for actual deployment).
# telegram_notify is lazy-imported inside cmd_* (needs `requests`).

MAX_DAILY_MULTIPLIER = 2
BATCH_SIZE = 10
# Account monthly spend cap in VND (env override; default 6,000,000).
# VND is the skill's currency everywhere a user sees a number. Used by the
# guardrail so the cap is a real ceiling, not derived from the proposed campaign.
ACCOUNT_MONTHLY_CAP = float(os.getenv("MONTHLY_BUDGET", "6000000"))


def generate_ad_copy(plan: Dict[str, Any], niche: str) -> List[Dict[str, Any]]:
    """Generate 10-15 ad copy variations based on research plan.

    TODO: Integrate with Hermes LLM for copy generation
    """
    print(f"[COPY] Generating ad copy variations for '{niche}'")

    # Placeholder copy generation - would be replaced by Hermes LLM (agent-layered).
    # Accepts BOTH old plan shape (keywords[]) and research.py shape (keyword_seeds).
    variations = []
    if "keyword_seeds" in plan:
        kw_map = plan["keyword_seeds"]
        keywords = [k for cat in ("branded", "non_branded", "intent")
                    for k in kw_map.get(cat, [])]
    else:
        keywords = [kw.get("keyword", str(kw)) for kw in plan.get("keywords", [])]
    competitors = plan.get("competitors", [])
    location = plan.get("location") or {"vn": "Vietnam"}.get(
        plan.get("market", "vn"), "Vietnam")

    # Generate variations with different angles
    angles = [
        "Expert", "Professional", "Local", "Affordable", "Quality",
        "Reliable", "Fast", "Experienced", "Certified", "Trusted"
    ]

    for i in range(12):
        angle = angles[i % len(angles)]
        # Google Ads RSA limits: headline ≤30 chars, description ≤90. Truncate
        # placeholder copy to stay policy-valid (real copy via agent-layered LLM).
        n = niche.title()
        headlines = [
            f"{angle} {n}"[:30],
            f"Best {n}"[:30],
            f"{n} {location}"[:30],
        ]

        descriptions = [
            f"Professional {niche} in {location}. Book a test drive today!"[:90],
            f"Local {niche} experts. Quality service, competitive price."[:90],
        ]

        variations.append({
            "headlines": headlines,
            "descriptions": descriptions,
            "path1": niche.replace(" ", "-"),
            "path2": angle.lower()
        })

    print(f"[COPY] Generated {len(variations)} variations (placeholder; "
          f"agent layers real Vinfast copy via LLM)")
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
    print(f"[BUDGET] Checking guardrails: daily {daily_budget:,.0f} VND "
          f"(account cap {ACCOUNT_MONTHLY_CAP:,.0f} VND/mo)")
    existing_monthly = get_total_monthly_budget(db)        # EXISTING campaigns only
    proposed_monthly = existing_monthly + (daily_budget * 30)
    if proposed_monthly > ACCOUNT_MONTHLY_CAP:
        print(f"⚠️ BUDGET GUARD: account cap exceeded")
        print(f"   Existing {existing_monthly:,.0f} VND/mo + proposed "
              f"{daily_budget*30:,.0f} VND/mo = {proposed_monthly:,.0f} VND/mo")
        print(f"   Cap {ACCOUNT_MONTHLY_CAP:,.0f} VND/mo (MONTHLY_BUDGET env)")
        print(f"   → Reduce daily budget or pause another campaign.")
        return False
    print(f"[BUDGET] OK — projected {proposed_monthly:,.0f} VND/mo ≤ "
          f"cap {ACCOUNT_MONTHLY_CAP:,.0f} VND/mo")
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


def _research_to_deploy_plan(research_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Transform research.py output shape → deploy_full_campaign plan shape.

    research.py emits {model, budget:{monthly_vnd,monthly_usd,daily_usd},
    keyword_seeds:{branded,non_branded,intent,competitor_conquest,negative}, market}.
    deploy_full_campaign expects {niche, location, budget_plan:{daily_budget,
    estimated_cpc_range}, keywords:[{keyword}]}.
    """
    model = research_plan.get("model", {})
    budget = research_plan.get("budget", {})
    seeds = research_plan.get("keyword_seeds", {})
    keywords = [{"keyword": k} for cat in ("branded", "non_branded", "intent")
                for k in seeds.get(cat, [])]
    # VND is the pipeline currency. research.py emits daily_vnd + cpc_vnd_used;
    # fall back to deriving from monthly_vnd for older plan files.
    daily = budget.get("daily_vnd") or round((budget.get("monthly_vnd", 0) or 0) / 30)
    # VN-aware CPC in VND: research.py sets cpc_vnd_used per market (VN ~12,500).
    cpc = budget.get("cpc_vnd_used", 12500)
    return {
        "niche": model.get("name", "vinfast"),
        "location": {"vn": "Vietnam"}.get(research_plan.get("market", "vn"), "Vietnam"),
        "budget_plan": {"daily_budget": daily, "estimated_cpc_range": [cpc, round(cpc * 1.4)]},
        "keywords": keywords,
    }


def _generate_and_screen(plan: Dict[str, Any], niche: str, db, daily_budget: float):
    """Shared create-mode steps: guardrail → generate copy → policy screen.

    Returns (variations, campaign_id) or None on guardrail/policy failure.
    """
    if not run_budget_guardrails(db, daily_budget):
        return None
    variations = generate_ad_copy(plan, niche)
    print("\n[POLICY] Screening ad copy for policy violations")
    for i, var in enumerate(variations):
        result = screen_ad_copy(var["headlines"], var["descriptions"])
        if not result["passed"]:
            print(f"⚠️ Variation {i+1} failed policy check:")
            for v in result["violations"]:
                print(f"   • {v}")
            print("Policy violations found. Fix before requesting approval.")
            return None
        if result["warnings"]:
            print(f"ℹ️ Variation {i+1} warnings: {', '.join(result['warnings'])}")
    campaign_id = f"{niche.replace(' ', '-')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    return variations, campaign_id


def cmd_create(args) -> int:
    """Default mode: generate copy → write pending approval → notify → exit 0.

    Headless-safe (no input()). Does NOT deploy — a human must run
    `--approve <uuid> --indices ...` to deploy. This is the async gate.
    """
    from telegram_notify import send_approval_request  # lazy (needs requests)

    if not args.plan:
        print("Error: --plan <strategy.json> required in create mode.")
        return 1
    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"Error: Plan file not found: {plan_path}")
        return 1
    with open(plan_path) as f:
        plan = json.load(f)

    script_dir = Path(__file__).parent
    # Guardrail reads the authoritative campaigns store (campaigns-local.db,
    # written by monitor after each deploy). The old ad-copy-learning.db never
    # received campaign rows → cap always saw $0 existing → decorative (C1 fix).
    db = init_db(script_dir.parent / "data" / "campaigns-local.db")
    # VND everywhere: --budget and plan.monthly_vnd are both VND (no conversion).
    monthly_budget = args.budget or plan.get("budget", {}).get("monthly_vnd", 6000000)
    daily_budget = round(monthly_budget / 30)

    niche = plan.get("model", {}).get("name") or plan.get("niche") or args.niche or "vinfast"
    gs = _generate_and_screen(plan, niche, db, daily_budget)
    if not gs:
        return 1
    variations, campaign_id = gs

    uuid_ = write_pending(str(plan_path), niche, variations, campaign_id)
    print(f"\n📝 Pending approval written: {campaign_id}")
    print(f"   UUID: {uuid_}")
    print(f"   Approve: creator.py --approve {uuid_} --indices 1,3")
    print(f"   Reject:  creator.py --reject {uuid_}")
    print(f"   (expires in 24h)")
    send_approval_request(uuid_, niche, variations, campaign_id)
    return 0


def cmd_approve(uuid_: str, indices_str: str, mock: bool) -> int:
    """Approve mode: read pending → guardrail → deploy → notify.

    Holds an exclusive per-uuid lock (C3 fix) so two concurrent --approve runs
    can't both pass the 'pending' check and double-deploy (double spend).
    Re-checks the budget guardrail at deploy time (C4 fix): create-time
    approval doesn't guarantee the cap still holds when deploy actually runs
    (could be hours later, other campaigns may have been added).
    """
    from telegram_notify import send_deploy_result  # lazy (needs requests)

    with approval_lock(uuid_):
        rec = read_pending(uuid_)
        if not rec:
            print(f"❌ No pending approval for uuid {uuid_}")
            return 1
        if rec["status"] != "pending":
            print(f"❌ Approval {uuid_} is not pending (status={rec['status']}).")
            return 1
        # Parse indices
        try:
            indices = [int(x.strip()) - 1 for x in (indices_str or "").split(",") if x.strip()]
        except ValueError:
            print("❌ --indices must be comma-separated numbers (e.g. 1,3)")
            return 1
        variations = rec["variations"]
        valid = [i for i in indices if 0 <= i < len(variations)]
        if not valid:
            print(f"❌ No valid indices. Pick from 1..{len(variations)}.")
            return 1
        approved = [variations[i] for i in valid]

        with open(rec["plan_path"]) as f:
            research_plan = json.load(f)
        plan = _research_to_deploy_plan(research_plan)  # adapt shape for deploy

        # C4: re-check budget cap at deploy time against the authoritative store.
        daily = plan["budget_plan"]["daily_budget"]
        guard_db = init_db(Path(__file__).parent.parent / "data" / "campaigns-local.db")
        if not run_budget_guardrails(guard_db, daily):
            msg = ("Budget cap exceeded at approve time — deploy blocked. "
                   "Pause another campaign or raise MONTHLY_BUDGET (VND).")
            print(f"❌ {msg}")
            send_deploy_result(uuid_, False, msg)
            return 1

        try:
            result = deploy_campaign(plan, approved, allow_mock=mock)
        except RuntimeError as e:
            print(f"\n❌ Cannot deploy: {e}")
            send_deploy_result(uuid_, False, str(e))
            return 1
        # Atomic status transition (still under the lock). Wrapped so a record-
        # write failure doesn't mask a successful deploy from the notify below.
        try:
            mark_status(uuid_, "deployed" if result.get("success") else "rejected", valid)
        except Exception as e:
            print(f"⚠️ mark_status failed ({e}) — record may still show 'pending'.")
        # C1/C4 completion: persist the deployed campaign so the budget guardrail
        # counts it on the NEXT approve. Without this, rapid sequential approves
        # of different uuids each read $0 existing and bypass MONTHLY_BUDGET.
        # Mock deploys aren't real campaigns → don't record them.
        if result.get("success") and not mock:
            try:
                camp_db = init_db(Path(__file__).parent.parent / "data" / "campaigns-local.db")
                save_campaign(camp_db, {
                    "campaign_id": rec.get("campaign_id"),
                    "niche": plan.get("niche", ""),
                    "location": str(plan.get("location", "")),
                    "monthly_budget": daily * 30,
                    "daily_budget": daily,
                    "status": "active",
                })
            except Exception as e:
                print(f"⚠️ Could not save campaign to local DB — guardrail may "
                      f"under-count existing spend next run: {e}")

    if result.get("success"):
        detail = (f"{result.get('keywords_created',0)} kw, {result.get('ads_created',0)} ads"
                  + (" [MOCK]" if mock else ""))
        print(f"\n✅ Deployed: {result.get('campaign_resource_name')} ({detail})")
        send_deploy_result(uuid_, True, detail)
        return 0
    else:
        print(f"\n❌ Deploy failed: {result.get('error', 'unknown')}")
        send_deploy_result(uuid_, False, result.get("error", "unknown"))
        return 1


def cmd_reject(uuid_: str) -> int:
    """Reject mode: mark pending rejected + notify. No deploy."""
    from telegram_notify import send_text  # lazy (needs requests)
    if not read_pending(uuid_):
        print(f"❌ No pending approval for uuid {uuid_}")
        return 1
    mark_status(uuid_, "rejected")
    print(f"❌ Rejected {uuid_} — nothing deployed.")
    send_text(f"❌ Approval {uuid_} bị từ chối — không deploy.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Google Ads Campaign Creator (async approval)")
    parser.add_argument("--plan", type=str, help="Research strategy JSON (create mode)")
    parser.add_argument("--budget", type=int, help="Override monthly budget VND (create mode)")
    parser.add_argument("--niche", type=str, help="Target niche (create mode)")
    parser.add_argument("--location", type=str, default="United States", help="Location")
    parser.add_argument("--mock", action="store_true",
                        help="Mock deploy (no real API, no spend)")
    parser.add_argument("--approve", metavar="UUID", help="Approve pending uuid + deploy")
    parser.add_argument("--reject", metavar="UUID", help="Reject pending uuid (no deploy)")
    parser.add_argument("--indices", type=str, help="Comma-separated variation indices (with --approve)")
    args = parser.parse_args()

    if args.approve:
        return cmd_approve(args.approve, args.indices, args.mock)
    if args.reject:
        return cmd_reject(args.reject)
    return cmd_create(args)


if __name__ == "__main__":
    sys.exit(main())