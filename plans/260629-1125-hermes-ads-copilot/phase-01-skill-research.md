# Phase 01 — Hermes Skill: google-ads-research

## Context
- Parent: [plan.md](plan.md). Depends: none (can start in parallel with Phase 00).
- Scenario criticals: no API dependency (web search + LLM only). Output = structured JSON plan for human review.
- Blocks: Phase 03 (creator skill consumes research output as input).

## Overview
Build the first Hermes skill: `google-ads-research`. Uses Hermes web search tools
and LLM reasoning (NO Google Ads API) to produce keyword plans, competitor analysis,
audience targeting, and budget recommendations. Invoked on demand via
`/google-ads research`. Output = structured JSON plan saved to file, presented
to human for review before creator skill uses it.

## Key Insights
- **No API needed**: research runs purely on web search + LLM. This means Phase 01
  is unblocked and can start immediately alongside Phase 00.
- **LLM reasoning > raw search**: Hermes already has web_search tool. This skill
  orchestrates multiple searches, synthesizes results, and applies advertising
  knowledge (search intent, competition levels, bid estimates).
- **Human review gate**: research output is saved to JSON file → shown to user →
  user approves/edits → creator skill reads approved plan. Never auto-proceed.
- **Budget math is deterministic**: `daily_budget = monthly_budget / 30`.
  Bid strategy recommendation based on account age (new → Manual CPC).

## Requirements
- **Functional**: keyword research, competitor analysis, audience targeting, budget planning.
- **Non-functional**: no cron needed (on-demand), no external API deps, structured JSON output,
  <200 lines per Python file, stdlib-first (only `json`, `pathlib`, `sys`).

## Architecture
```
skills/research/google-ads/
├── SKILL.md                          # skill manifest (YAML frontmatter)
├── scripts/
│   └── research.py                   # main orchestrator
└── references/
    └── keyword-methodology.md         # methodology docs for keyword research
```

Data flow:
```
User invokes "/google-ads research --niche 'web design agency'"
  → research.py parses args
  → LLM generates seed keywords from niche description
  → web_search expands each seed keyword
  → LLM classifies intent (transactional/informational/navigational)
  → LLM estimates competition (low/med/high based on ad count)
  → LLM analyzes competitor positioning (top 5 ads from search)
  → LLM recommends audience targeting (demo, location, interests)
  → LLM calculates budget recommendation
  → Output: JSON plan saved to data/google-ads-research-{date}.json
  → Present summary to user → wait for approval
```

## Related Code Files
- **Create**: `skills/research/google-ads/SKILL.md`
- **Create**: `skills/research/google-ads/scripts/research.py`
- **Create**: `skills/research/google-ads/references/keyword-methodology.md`
- **Create**: `skills/research/google-ads/data/` (output directory, gitignored)

## Interfaces

### Consumes
- CLI args: `--niche <str>`, `--location <str>`, `--budget <int>`, `--goal <str>`
- Environment: `HERMES_DATA_DIR` (default: `skills/research/google-ads/data/`)
- Hermes tools: `web_search` (available at runtime via agent context)

### Produces
- `data/google-ads-research-{YYYY-MM-DD}.json`:
  ```json
  {
    "niche": "web design agency",
    "location": "Austin, TX",
    "monthly_budget": 500,
    "generated_at": "2026-06-29T12:00:00Z",
    "keywords": [
      {
        "keyword": "web design services austin",
        "search_volume_estimate": "high",
        "competition": "high",
        "intent": "transactional",
        "suggested_bid_cpc": 8.50,
        "match_type": "phrase"
      }
    ],
    "competitors": [
      {
        "name": "Competitor A",
        "headline": "Best Web Design in Austin",
        "positioning": "premium quality, local focus",
        "gaps": ["no mention of pricing", "no free consultation offer"]
      }
    ],
    "audience": {
      "demographics": {"age": "25-54", "income": "medium-high"},
      "locations": ["Austin, TX", "50mi radius"],
      "interests": ["small business owners", "startups", "entrepreneurs"]
    },
    "budget_plan": {
      "daily_budget": 16.67,
      "bid_strategy": "Manual CPC",
      "estimated_monthly_clicks": 150,
      "estimated_cpc_range": [4.00, 12.00],
      "estimated_monthly_leads": 15,
      "estimated_cpl": 33.33
    }
  }
  ```

## Implementation Steps

### Step 1: Create SKILL.md (30 min)
```yaml
---
name: google-ads-research
description: "Google Ads research skill: keyword, competitor, audience, budget analysis via web search + LLM"
version: 0.1.0
author: Hermes Agent
tags: [google-ads, keyword-research, competitor-analysis, hermes-skill]
platforms: [linux, macos, windows]
---
```
Sections: When to Use, Prerequisites, How to Run, Research Capabilities, Output Format.

### Step 2: Create research.py orchestrator (2h)

Core function structure:
```python
# scripts/research.py
import json, pathlib, sys
from datetime import datetime

def main():
    niche = sys.argv[2] if len(sys.argv) > 2 else input("Niche: ")
    location = sys.argv.get_flag("--location", "United States")
    budget = int(sys.argv.get_flag("--budget", 500))
    goal = sys.argv.get_flag("--goal", "leads")

    plan = run_research(niche, location, budget, goal)
    save_plan(plan)
    present_summary(plan)

def run_research(niche, location, budget, goal):
    """Orchestrates 4 research phases via LLM + web_search."""
    keywords = research_keywords(niche, location)
    competitors = analyze_competitors(niche, location)
    audience = determine_audience(niche, location, goal)
    budget_plan = calculate_budget(budget, keywords)

    return {
        "niche": niche,
        "location": location,
        "monthly_budget": budget,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "keywords": keywords,
        "competitors": competitors,
        "audience": audience,
        "budget_plan": budget_plan,
    }

def research_keywords(niche, location):
    """Phase 1: Keyword research via web search + LLM classification."""
    # Step 1: LLM generates 10-15 seed keywords from niche description
    seeds = llm_generate_seed_keywords(niche)

    # Step 2: web_search each seed → count ads on SERP, related searches
    expanded = []
    for seed in seeds:
        results = web_search(f"{seed} {location}")  # Hermes tool
        expanded.extend(extract_related_keywords(results))
        expanded.append(classify_keyword(seed, results))

    # Step 3: LLM classifies intent + estimates competition
    classified = llm_classify_keywords(expanded)

    # Step 4: Deduplicate, filter low-value (informational intent), sort by priority
    return deduplicate_and_rank(classified)

def analyze_competitors(niche, location):
    """Phase 2: Competitor analysis via web search."""
    results = web_search(f"{niche} services {location}")
    ads = extract_ads_from_results(results)  # top 5 ad results
    return llm_analyze_positioning(ads)

def determine_audience(niche, location, goal):
    """Phase 3: Audience targeting recommendation via LLM reasoning."""
    return llm_recommend_audience(niche, location, goal)

def calculate_budget(budget, keywords):
    """Phase 4: Deterministic budget math + LLM bid estimates."""
    daily = round(budget / 30, 2)
    max_daily = round(daily * 2, 2)  # budget guardrail

    avg_cpc = estimate_average_cpc(keywords)  # LLM estimates from competition data
    estimated_clicks = int(budget / avg_cpc)
    estimated_leads = int(estimated_clicks * 0.10)  # 10% conversion rate assumption

    return {
        "daily_budget": daily,
        "max_daily_budget": max_daily,
        "bid_strategy": "Manual CPC",
        "estimated_monthly_clicks": estimated_clicks,
        "estimated_cpc_range": [round(avg_cpc * 0.7, 2), round(avg_cpc * 1.3, 2)],
        "estimated_monthly_leads": estimated_leads,
        "estimated_cpl": round(budget / max(estimated_leads, 1), 2),
    }
```

### Step 3: Create keyword-methodology.md (45 min)
Document:
- Seed keyword generation framework (problem-based, solution-based, local modifier)
- Search intent classification (transactional vs informational vs navigational)
- Competition estimation heuristic (ad count on SERP, domain authority of advertisers)
- Match type recommendations (exact for high-intent, phrase for mid-intent, broad for discovery — but default to phrase for new accounts)
- Negative keyword strategy (informational queries to exclude)

### Step 4: Wire into Hermes skill system (30 min)
- Ensure SKILL.md follows polymarket-signals frontmatter pattern
- Add to Hermes skill registry (if one exists)
- Test invocation: `/google-ads research --niche "web design agency" --location "Austin, TX" --budget 500`

## Todo
- [ ] Create `skills/research/google-ads/SKILL.md` with YAML frontmatter
- [ ] Create `scripts/research.py` — main orchestrator with CLI arg parsing
- [ ] Implement `research_keywords()` — seed generation + web search + classification
- [ ] Implement `analyze_competitors()` — SERP ad extraction + LLM positioning analysis
- [ ] Implement `determine_audience()` — demographic/location/interest recommendation
- [ ] Implement `calculate_budget()` — deterministic daily budget + bid estimation
- [ ] Create `references/keyword-methodology.md` — methodology documentation
- [ ] Create `data/` output directory (gitignored)
- [ ] Test: run full research flow with test niche
- [ ] Verify JSON output is valid and complete

## Success Criteria
- `/google-ads research --niche "test niche"` produces valid JSON in `data/`
- JSON contains all 4 sections: keywords, competitors, audience, budget_plan
- Keywords classified by intent (transactional/informational/navigational)
- Budget calculation uses hardcoded formula: `daily = monthly/30`, `max_daily = daily*2`
- Competitor analysis includes positioning + gaps
- research.py <200 lines (split if needed)
- No external API dependencies (web search + LLM only)

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| Web search returns low-quality results for obscure niches | Med | LLM compensates with domain knowledge. Flag if <5 keywords found. |
| CPC estimates inaccurate (no real data) | Med | Clearly label as "estimates". User adjusts in approval step. |
| LLM generates too many/all informational keywords | Med | Filter: keep only transactional + commercial investigation intent. |
| Competitor ad scraping misses dynamic ads | Low | web_search captures snapshot. Good enough for positioning analysis. |

## Security
- No credentials needed for this skill
- No user data sent to external APIs (web search is Hermes internal tool)
- Output JSON contains no PII

## Next Steps
- Phase 02 (Cloudflare infra) — independent, can run in parallel
- Phase 03 (creator skill) — consumes research JSON output as campaign spec
