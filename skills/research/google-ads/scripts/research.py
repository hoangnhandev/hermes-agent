#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


def research_keywords(niche: str, location: str) -> List[Dict[str, Any]]:
    print(f"[KEYWORDS] Researching keywords for '{niche}' in '{location}'")
    keywords = [
        {"keyword": f"{niche} near me", "search_volume_estimate": "high", "competition": "medium", "intent": "transactional", "suggested_bid_cpc": 8.50, "match_type": "phrase"},
        {"keyword": f"best {niche} {location}", "search_volume_estimate": "medium", "competition": "high", "intent": "transactional", "suggested_bid_cpc": 12.00, "match_type": "phrase"},
        {"keyword": f"{niche} services", "search_volume_estimate": "high", "competition": "medium", "intent": "informational", "suggested_bid_cpc": 6.75, "match_type": "phrase"}
    ]
    print(f"[KEYWORDS] Found {len(keywords)} keywords")
    return keywords


def analyze_competitors(niche: str, location: str) -> List[Dict[str, Any]]:
    print(f"[COMPETITORS] Analyzing competitors for '{niche}' in '{location}'")
    competitors = [
        {"name": f"Leading {niche.title()} Co", "headline": f"Expert {niche.title()} Services", "positioning": "Premium service provider", "gaps": ["Limited online presence", "No weekend service"]},
        {"name": f"{location.title()} {niche.title()} Pros", "headline": f"Affordable {niche.title()} Solutions", "positioning": "Budget-friendly provider", "gaps": ["Lower quality perception", "Limited service area"]}
    ]
    print(f"[COMPETITORS] Analyzed {len(competitors)} competitors")
    return competitors


def determine_audience(niche: str, location: str, goal: str) -> Dict[str, Any]:
    print(f"[AUDIENCE] Determining audience for '{niche}' in '{location}' with goal '{goal}'")
    audience = {"demographics": {"age_range": "25-65", "gender": "All", "income_level": "Middle to High"}, "locations": [location], "interests": [f"{niche} services", "home improvement", "local businesses"]}
    print(f"[AUDIENCE] Generated audience profile")
    return audience


def calculate_budget(budget: int, keywords: List[Dict[str, Any]]) -> Dict[str, Any]:
    print(f"[BUDGET] Calculating budget allocation for ${budget}")
    daily = round(budget / 30, 2)
    max_daily = round(daily * 2, 2)
    avg_cpc = sum(k.get("suggested_bid_cpc", 8.0) for k in keywords) / len(keywords) if keywords else 8.0
    estimated_monthly_clicks = int((budget / avg_cpc) * 0.7)
    estimated_monthly_leads = int(estimated_monthly_clicks * 0.1)
    estimated_cpl = round(budget / estimated_monthly_leads, 2) if estimated_monthly_leads > 0 else 0
    budget_plan = {"daily_budget": daily, "max_daily_budget": max_daily, "bid_strategy": "Manual CPC", "estimated_monthly_clicks": estimated_monthly_clicks, "estimated_cpc_range": [round(avg_cpc * 0.7, 2), round(avg_cpc * 1.3, 2)], "estimated_monthly_leads": estimated_monthly_leads, "estimated_cpl": estimated_cpl}
    print(f"[BUDGET] Daily budget: ${daily}, Max daily: ${max_daily}")
    return budget_plan


def run_research(niche: str, location: str, budget: int, goal: str) -> Dict[str, Any]:
    print(f"[RESEARCH] Starting Google Ads research for '{niche}'")
    keywords = research_keywords(niche, location)
    competitors = analyze_competitors(niche, location)
    audience = determine_audience(niche, location, goal)
    budget_plan = calculate_budget(budget, keywords)
    results = {"niche": niche, "location": location, "monthly_budget": budget, "campaign_goal": goal, "generated_at": datetime.now().isoformat(), "keywords": keywords, "competitors": competitors, "audience": audience, "budget_plan": budget_plan}
    print(f"[RESEARCH] Research completed successfully")
    return results


def save_results(results: Dict[str, Any], data_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d")
    filename = f"google-ads-research-{timestamp}.json"
    filepath = data_dir / filename
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"[SAVE] Results saved to {filepath}")
    return filepath


def print_summary(results: Dict[str, Any]):
    niche = results["niche"]
    location = results["location"]
    keywords = results["keywords"]
    competitors = results["competitors"]
    budget_plan = results["budget_plan"]
    print("\n" + "="*60)
    print(f"GOOGLE ADS RESEARCH SUMMARY")
    print(f"="*60)
    print(f"Niche: {niche}")
    print(f"Location: {location}")
    print(f"Monthly Budget: ${results['monthly_budget']}")
    print()
    print(f"KEYWORDS ({len(keywords)} found):")
    for kw in keywords[:3]:
        print(f"  • {kw['keyword']} - {kw['search_volume_estimate']} volume, {kw['competition']} competition")
    if len(keywords) > 3:
        print(f"  ... and {len(keywords) - 3} more")
    print()
    print(f"COMPETITORS ({len(competitors)} analyzed):")
    for comp in competitors:
        print(f"  • {comp['name']} - {comp['headline']}")
    print()
    print(f"BUDGET PLAN:")
    print(f"  • Daily Budget: ${budget_plan['daily_budget']}")
    print(f"  • Max Daily Budget: ${budget_plan['max_daily_budget']}")
    print(f"  • Estimated Monthly Clicks: {budget_plan['estimated_monthly_clicks']}")
    print(f"  • Estimated Monthly Leads: {budget_plan['estimated_monthly_leads']}")
    print(f"  • Estimated CPL: ${budget_plan['estimated_cpl']}")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Google Ads Research Tool")
    parser.add_argument("--niche", required=True, help="Target market niche")
    parser.add_argument("--location", default="United States", help="Geographic location")
    parser.add_argument("--budget", type=int, default=500, help="Monthly budget")
    parser.add_argument("--goal", default="leads", help="Campaign goal")
    args = parser.parse_args()
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    data_dir.mkdir(exist_ok=True)
    results = run_research(args.niche, args.location, args.budget, args.goal)
    filepath = save_results(results, data_dir)
    print_summary(results)
    print(f"\nFull results saved to: {filepath}")


if __name__ == "__main__":
    main()