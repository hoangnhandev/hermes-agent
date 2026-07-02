#!/usr/bin/env python3
"""One-shot orchestrator: budget → strategy → pending approval gate.

Lets a user (or Violet-chan via Telegram) say "5 triệu cho vinfast" and get an
optimal campaign STAGED in a single call, without driving the multi-step CLI
by hand. Chains the deterministic research spine into creator's async approval
gate. Does NOT deploy or spend — a human must run `creator.py --approve <uuid>`
to actually spend (money-safety gate). No Google Ads creds needed for this
stage (research + draft only); creds are only required at --approve time.

Pipeline:
  1. research.py --budget N --model M   → data/strategy-{M}-{date}.json
  2. creator.py --plan <json> --budget N → pending record + Telegram approval
  3. prints the approve command (UUID) so the user/Violet can finish on confirm.

Usage:
  python3 stage_campaign.py --budget 5000000                 # VF3 default, VN market (5 triệu)
  python3 stage_campaign.py --budget 5000000 --model vf5
  python3 stage_campaign.py --budget 10000000 --goal-sales 2  # + honest goal check
"""
from __future__ import annotations
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from _env import load_google_ads_env  # so creator's telegram_notify (subprocess) inherits creds

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
PY = sys.executable


def _run_research(budget: int, model: str, goal_sales: int | None) -> Path | None:
    """Step 1: run research.py → return the saved strategy JSON path, or None."""
    cmd = [PY, str(SCRIPT_DIR / "research.py"),
           "--budget", str(budget), "--model", model]
    if goal_sales:
        cmd += ["--goal-sales", str(goal_sales)]
    # Stream research output so the user sees the honest projections live.
    rc = subprocess.run(cmd, cwd=str(SCRIPT_DIR)).returncode
    if rc != 0:
        print(f"❌ research.py thất bại (exit {rc})")
        return None
    # research.py names files strategy-{model}-{YYYY-MM-DD}.json via datetime.now().
    date = datetime.now().strftime("%Y-%m-%d")
    plan = DATA_DIR / f"strategy-{model}-{date}.json"
    if not plan.exists():
        print(f"❌ Không tìm thấy file strategy: {plan}")
        return None
    return plan


def _run_creator(plan_path: Path, budget: int) -> str | None:
    """Step 2: run creator.py create-mode (pending + Telegram) → return UUID."""
    cmd = [PY, str(SCRIPT_DIR / "creator.py"),
           "--plan", str(plan_path), "--budget", str(budget)]
    # Capture to extract the UUID, then echo so the user sees the full notice.
    out = subprocess.run(cmd, cwd=str(SCRIPT_DIR), capture_output=True, text=True)
    print(out.stdout, end="")
    if out.stderr:
        print(out.stderr, end="", file=sys.stderr)
    if out.returncode != 0:
        print(f"❌ creator.py thất bại (exit {out.returncode})")
        return None
    m = re.search(r"UUID:\s*(\S+)", out.stdout)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Vinfast Ads one-shot: budget → strategy → approval gate (no spend)")
    ap.add_argument("--budget", type=int, required=True,
                    help="Monthly budget in VND (e.g. 5000000 = 5 triệu)")
    ap.add_argument("--model", default=None,
                    help="Vinfast model slug (default: auto-pick optimal by budget)")
    ap.add_argument("--goal-sales", type=int, default=None,
                    help="Target vehicle sales/month for honest goal check")
    args = ap.parse_args()

    # Load google-ads.env (TELEGRAM_*, GOOGLE_ADS_*) into os.environ so the
    # creator.py subprocess inherits creds — otherwise telegram_notify skips
    # the approval ping when this script is invoked directly (not via wrapper).
    # setdefault: real env (e.g. set by Hermes gateway) wins over the file.
    load_google_ads_env()

    # Auto-pick the optimal model for the budget when --model is omitted, then
    # pass it explicitly to research.py (so both agree on the strategy file).
    if args.model is None:
        from _budget_calc import recommend_model_for_budget
        args.model, reason = recommend_model_for_budget(args.budget)
        print(f"🤖 Tự chọn model tối ưu cho {args.budget:,} VND:\n   {reason}\n")

    line = "═" * 60
    print(f"\n{line}\n🧠 Bước 1/2 — Nghiên cứu chiến lược ({args.budget:,} VND)\n{line}")
    plan_path = _run_research(args.budget, args.model, args.goal_sales)
    if not plan_path:
        return 1

    print(f"\n{line}\n🚀 Bước 2/2 — Tạo chiến dịch + chờ duyệt\n{line}")
    uuid_ = _run_creator(plan_path, args.budget)
    if not uuid_:
        return 1

    print(f"\n{line}\n✅ ĐÃ STAGE chiến dịch {args.model.upper()} — {args.budget:,} VND/tháng")
    print("   📲 Kiểm tra Telegram để duyệt ad copy (nếu đã set bot).")
    print("   Deploy (chi tiền thật — cần Google Ads creds) khi sẵn sàng:")
    print(f"     creator.py --approve {uuid_} --indices 1,3")
    print(f"{line}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
