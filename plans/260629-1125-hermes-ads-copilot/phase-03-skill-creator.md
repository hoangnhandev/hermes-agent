# Phase 03 — Hermes Skill: google-ads-creator

## Context
- Parent: [plan.md](plan.md). Depends: Phase 00 (API access + credentials).
- Scenario criticals: C1 (budget hallucination), C3 (policy violation), H1 (rate limit), H9 (API version).
- Blocks: Phase 04 (monitor needs created campaigns to track).

## Overview
Extend the google-ads skill with campaign creation capabilities: read approved research
plan → generate ad copy via LLM → policy-screen against restricted terms → present to
human for approval → deploy approved copy via Google Ads API. Budget guardrails hardcoded.
Partial failure rollback. Sync campaign structure to D1 after creation.

## Key Insights
- **Human-in-the-loop is mandatory**: LLM generates 10-15 headline/description variations.
  Human picks which to deploy. No auto-deploy. This is the Tier 1 copilot contract.
- **Policy screening happens BEFORE approval**: saves time by rejecting obvious violations
  (misleading claims, disallowed content, character limits) before human reviews.
- **Budget guardrails are hardcoded per-campaign**: `max_daily = campaign_monthly_budget / 30 * 2`.
  Guardrail checks BOTH per-campaign AND account total (prevents one campaign from consuming
  another's budget). Not configurable by LLM.
  Not overridable by LLM. If API call would exceed, abort.
- **Batch API calls in groups of 10**: Google Ads API mutates in batches. Partial failures within
  a batch require rollback of that batch only (not the whole campaign).
- **Local SQLite learning store**: approved + rejected copy saved with performance data.
  Future iterations use this to improve copy generation.

## Requirements
- **Functional**: campaign creation, ad group creation, ad copy generation, policy screening,
  human approval flow, deployment via API, D1 sync.
- **Non-functional**: <200 lines per Python file, retry with exponential backoff on 429,
  rollback on partial failure, all operations logged.

## Architecture
```
skills/research/google-ads/
├── SKILL.md                            # updated with creator commands
├── scripts/
│   ├── research.py                     # Phase 01 (existing)
│   ├── creator.py                      # main orchestrator: plan → copy → screen → approve → deploy
│   ├── policy_check.py                 # Google Ads policy screening
│   └── deploy.py                      # Google Ads API deployment wrapper
├── data/
│   ├── google-ads-research-{date}.json # Phase 01 output (input to creator)
│   ├── ad-copy-learning.db             # SQLite: approved/rejected copy + performance
│   └── campaigns-local.db              # SQLite: local campaign mirror (source of truth)
└── references/
    ├── keyword-methodology.md          # Phase 01 (existing)
    └── restricted-terms.md             # Google Ads policy: disallowed content list
```

Data flow:
```
User: "/google-ads create --plan data/google-ads-research-2026-06-29.json"
  → creator.py reads research plan
  → LLM generates 10-15 ad copy variations (headlines + descriptions)
  → policy_check.py screens each variation
  → Present approved-pending variations to user (numbered list)
  → User selects which to deploy (e.g. "1,3,5,8")
  → deploy.py creates campaign structure via Google Ads API:
      - Campaign (Search, Manual CPC, daily_budget)
      - Ad Groups (keyword grouping from research plan)
      - Keywords (phrase match, from research plan)
      - Ads (user-selected copy)
  → On success: sync campaign structure to D1 via POST /api/sync
  → On partial failure: rollback failed batch, report which succeeded
  → Save all copy (approved + rejected) to ad-copy-learning.db
```

## Related Code Files
- **Create**: `skills/research/google-ads/scripts/creator.py`
- **Create**: `skills/research/google-ads/scripts/policy_check.py`
- **Create**: `skills/research/google-ads/scripts/deploy.py`
- **Create**: `skills/research/google-ads/references/restricted-terms.md`
- **Update**: `skills/research/google-ads/SKILL.md` (add creator commands)
- **Read**: `google-ads.env` (API credentials from Phase 00)
- **Read**: `data/google-ads-research-*.json` (research output from Phase 01)

## Interfaces

### Consumes
- CLI args: `--plan <path>`, `--niche <str>` (if no plan file), `--budget <int>`
- Research plan JSON (from Phase 01 output)
- `google-ads.env` (OAuth credentials)
- User input: approval selection (which copy variations to deploy)

### Produces
- Google Ads API calls: campaign, ad_group, ad, keyword mutations
- POST /api/sync to D1 (campaign structure after creation)
- `ad-copy-learning.db` records (all generated copy + approval status)
- `campaigns-local.db` records (local campaign mirror)

## Implementation Steps

### Step 1: Update SKILL.md (15 min)
Add creator section to existing SKILL.md:
```yaml
# Add to frontmatter tags: [google-ads, campaign-creation, ad-copy, hermes-skill]
```
New sections:
- **Campaign Creation**: how to invoke creator, what it does, approval flow
- **Policy Screening**: what gets checked, how violations are flagged
- **Budget Guardrails**: hardcoded formula explanation

### Step 2: Create deploy.py — Google Ads API Wrapper (2h)

Core structure:
```python
# scripts/deploy.py
import sys, json, time
from google.ads.googleads.client import GoogleAdsClient

BATCH_SIZE = 10
MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds

def get_client(env_file="google-ads.env"):
    """Load Google Ads client from env file."""
    return GoogleAdsClient.load_from_env(env_file)

def create_campaign(client, customer_id, name, daily_budget_micros, bid_strategy="MANUAL_CPC"):
    """Create a Search campaign. Returns campaign resource name."""
    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")

    campaign = campaign_operation.create
    campaign.name = name
    campaign.advertising_channel_type = client.get_type("AdvertisingChannelTypeEnum").SEARCH
    campaign.status = client.get_type("CampaignStatusEnum").ENABLED
    campaign.manual_cpc.enhanced_cpc_enabled = False

    # Budget (in micros — $16.67 = 16,670,000 micros)
    budget_service = client.get_service("BudgetService")
    budget_operation = client.get_type("BudgetOperation")
    budget = budget_operation.create
    budget.amount_micros = daily_budget_micros
    budget.name = f"Budget - {name}"
    budget_response = budget_service.mutate_budgets(customer_id=customer_id, operations=[budget_operation])
    campaign.campaign_budget = budget_response.results[0].resource_name

    response = campaign_service.mutate_campaigns(customer_id=customer_id, operations=[campaign_operation])
    return response.results[0].resource_name

def create_ad_group(client, customer_id, campaign_resource_name, name, cpc_bid_micros):
    """Create an ad group within a campaign."""
    ad_group_service = client.get_service("AdGroupService")
    ad_group_operation = client.get_type("AdGroupOperation")

    ad_group = ad_group_operation.create
    ad_group.name = name
    ad_group.campaign = campaign_resource_name
    ad_group.type_ = client.get_type("AdGroupTypeEnum").SEARCH_STANDARD
    ad_group.status = client.get_type("AdGroupStatusEnum").ENABLED
    ad_group.cpc_bid_micros = cpc_bid_micros  # e.g. 8,500,000 = $8.50

    response = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[ad_group_operation])
    return response.results[0].resource_name

def create_keywords(client, customer_id, ad_group_resource_name, keywords):
    """Batch-create keywords. keywords = list of (text, match_type)."""
    keyword_service = client.get_service("AdGroupCriterionService")
    operations = []

    for text, match_type in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        criterion = op.create
        criterion.ad_group = ad_group_resource_name
        criterion.keyword.text = text
        criterion.keyword.match_type = getattr(
            client.get_type("KeywordMatchTypeEnum"), match_type  # PHRASE, EXACT, BROAD
        )
        criterion.status = client.get_type("AdGroupCriterionStatusEnum").ENABLED
        operations.append(op)

    # Batch in groups of BATCH_SIZE
    results = []
    for i in range(0, len(operations), BATCH_SIZE):
        batch = operations[i:i + BATCH_SIZE]
        response = retry_with_backoff(
            lambda: keyword_service.mutate_ad_group_criteria(customer_id=customer_id, operations=batch)
        )
        results.extend(response.results)

    return results

def create_ads(client, customer_id, ad_group_resource_name, ads):
    """Batch-create responsive search ads. ads = list of {headlines: [...], descriptions: [...]}."""
    ad_service = client.get_service("AdGroupAdService")
    operations = []

    for ad_data in ads:
        op = client.get_type("AdGroupAdOperation")
        ad = op.create
        ad.ad_group = ad_group_resource_name
        ad.status = client.get_type("AdGroupAdStatusEnum").ENABLED

        rsa = ad.ad.responsive_search_ad
        for h in ad_data["headlines"][:15]:
            headline = rsa.headlines.append(client.get_type("AdTextAsset"))
            headline.text = h[:30]  # max 30 chars
        for d in ad_data["descriptions"][:4]:
            desc = rsa.descriptions.append(client.get_type("AdTextAsset"))
            desc.text = d[:90]  # max 90 chars

        rsa.path1 = ad_data.get("path1", "")[:15]
        rsa.path2 = ad_data.get("path2", "")[:15]

        operations.append(op)

    results = []
    for i in range(0, len(operations), BATCH_SIZE):
        batch = operations[i:i + BATCH_SIZE]
        response = retry_with_backoff(
            lambda: ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=batch)
        )
        results.extend(response.results)

    return results

def retry_with_backoff(func, max_retries=MAX_RETRIES):
    """Retry with exponential backoff on rate limit (429) errors."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if "RATE_LIMIT_EXCEEDED" in str(e) and attempt < max_retries - 1:
                wait = BACKOFF_BASE ** (attempt + 1)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Failed after {max_retries} retries")
```

### Step 3: Create policy_check.py — Policy Screening (1.5h)

```python
# scripts/policy_check.py

# Load restricted terms from references/restricted-terms.md
# Categories:
#   1. Misleading claims: "guaranteed", "#1", "best", "free" (conditional)
#   2. Personal attributes: gender, age, race, religion, sexual orientation
#   3. Healthcare claims: cure, treat, prevent (for non-certified businesses)
#   4. Financial claims: specific returns, guaranteed profit
#   5. Character limits: headline 30, description 90, path 15

POLICY_RULES = {
    "disallowed_terms": [
        "guaranteed", "guarantee", "#1", "number one", "best ever",
        "free money", "get rich", "miracle", "cure",
    ],
    "conditional_terms": ["free"],  # OK if actually free
    "character_limits": {
        "headline": 30,
        "description": 90,
        "path": 15,
    },
    "required_disclaimers": [],  # add if niche requires
}

def screen_ad_copy(headlines, descriptions):
    """Screen ad copy against Google Ads policy rules.
    Returns: { passed: bool, violations: [...], warnings: [...] }
    """
    violations = []
    warnings = []

    all_text = " ".join(headlines + descriptions).lower()

    for term in POLICY_RULES["disallowed_terms"]:
        if term in all_text:
            violations.append(f"Disallowed term: '{term}'")

    for term in POLICY_RULES["conditional_terms"]:
        if term in all_text:
            warnings.append(f"Conditional term: '{term}' — verify actually free")

    # Character limits
    for i, h in enumerate(headlines):
        if len(h) > POLICY_RULES["character_limits"]["headline"]:
            violations.append(f"Headline {i+1} exceeds {30} chars ({len(h)})")

    for i, d in enumerate(descriptions):
        if len(d) > POLICY_RULES["character_limits"]["description"]:
            violations.append(f"Description {i+1} exceeds {90} chars ({len(d)})")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
    }
```

### Step 4: Create creator.py — Orchestrator (2.5h)

```python
# scripts/creator.py
import json, sys, sqlite3, pathlib
from datetime import datetime

MAX_DAILY_MULTIPLIER = 2  # hardcoded, never change

def main():
    plan_path = sys.argv.get_flag("--plan")
    budget = int(sys.argv.get_flag("--budget", 500))
    niche = sys.argv.get_flag("--niche")

    if plan_path:
        with open(plan_path) as f:
            plan = json.load(f)
    else:
        # Generate research inline (calls research.py logic)
        plan = run_research(niche, budget)

    # MULTI-CAMPAIGN: per-campaign budget guardrails
    # Check BOTH per-campaign cap AND account total
    daily_budget = round(budget / 30, 2)
    max_daily_per_campaign = round(daily_budget * MAX_DAILY_MULTIPLIER, 2)
    
    # Check account-level budget: sum of all active campaigns' daily budgets
    total_existing_daily = get_total_existing_daily_budget(db)
    total_monthly = get_total_monthly_budget(db) + budget
    max_daily_total = round(total_monthly / 30 * MAX_DAILY_MULTIPLIER, 2)
    
    if total_existing_daily + daily_budget > max_daily_total:
        print(f"⚠️ BUDGET GUARD: Adding ${daily_budget}/day exceeds account cap ${max_daily_total}/day")
        print(f"   Existing campaigns use ${total_existing_daily}/day")
        print(f"   Reduce new campaign budget or pause another campaign.")
        return None  # Block creation
    
    print(f"Campaign daily: ${daily_budget} | Cap: ${max_daily_per_campaign}")
    print(f"Account daily total: ${total_existing_daily + daily_budget} | Cap: ${max_daily_total}")

    # Generate ad copy variations via LLM
    variations = generate_ad_copy(plan, niche)
    # variations = [
    #   { "headlines": ["h1", "h2", "h3"], "descriptions": ["d1", "d2"], "path1": "path", "path2": "here" },
    #   ... (10-15 variations)
    # ]

    # Policy screen each variation
    screened = []
    for i, v in enumerate(variations):
        result = policy_check.screen_ad_copy(v["headlines"], v["descriptions"])
        v["policy"] = result
        if result["passed"]:
            screened.append(v)
        else:
            print(f"  Variation {i+1} REJECTED: {result['violations']}")

    if not screened:
        print("All variations failed policy screening. Aborting.")
        sys.exit(1)

    # Present to user for approval
    present_for_approval(screened)

    # Wait for user selection
    selection = input("Enter approved variation numbers (comma-separated): ")
    approved_indices = [int(x.strip()) - 1 for x in selection.split(",")]
    approved_variations = [screened[i] for i in approved_indices]

    # Confirm budget
    print(f"\nDeploying {len(approved_variations)} ad variations")
    print(f"Campaign: {plan['niche']} - Search Campaign")
    print(f"Daily budget: ${daily_budget} (max: ${max_daily})")
    confirm = input("Confirm deployment? (yes/no): ")
    if confirm.lower() != "yes":
        print("Aborted by user.")
        sys.exit(0)

    # Deploy via Google Ads API
    deploy_result = deploy_campaign(
        client=get_client(),
        customer_id=CUSTOMER_ID,
        plan=plan,
        daily_budget_micros=int(daily_budget * 1_000_000),
        cpc_bid_micros=int(plan["budget_plan"]["estimated_cpc_range"][0] * 1_000_000),
        ad_variations=approved_variations,
    )

    # Save to learning database
    save_to_learning_db(variations, approved_indices)

    # Sync to D1
    sync_to_d1(deploy_result)

    print(f"Campaign deployed: {deploy_result['campaign_name']}")
    print(f"Campaign ID: {deploy_result['campaign_id']}")

def generate_ad_copy(plan, niche):
    """LLM generates 10-15 ad copy variations based on research plan."""
    prompt = f"""Generate 10-15 Responsive Search Ad variations for: {niche}

Context from research:
- Top keywords: {plan['keywords'][:10]}
- Competitor positioning: {plan['competitors'][:3]}
- Audience: {plan['audience']}

For each variation, provide:
- 3 headlines (max 30 chars each)
- 2 descriptions (max 90 chars each)
- 2 path components (max 15 chars each)

Format as JSON array. Focus on unique value propositions.
Avoid: guaranteed, #1, best ever, misleading claims.
Include: specific local references, actionable CTAs, social proof hints."""

    # LLM generates variations → parse JSON → return list of dicts
    return llm_generate(prompt)

def present_for_approval(variations):
    """Pretty-print variations for human review."""
    for i, v in enumerate(variations):
        print(f"\n--- Variation {i+1} ---")
        for h in v["headlines"]:
            print(f"  H: {h} ({len(h)}/30)")
        for d in v["descriptions"]:
            print(f"  D: {d} ({len(d)}/90)")
        if v.get("policy", {}).get("warnings"):
            print(f"  ⚠ Warnings: {v['policy']['warnings']}")
```

### Step 5: Create restricted-terms.md (30 min)

Reference doc with:
- Google Ads prohibited content categories (personal attributes, healthcare, financial)
- Misleading claims list
- Character limits table (headline 30, description 90, path 15)
- Industry-specific restrictions (for common niches)
- Links to official Google Ads policy pages

### Step 6: Sync to D1 After Creation (30 min)

After successful campaign creation, POST campaign structure to D1:
```python
def sync_to_d1(deploy_result):
    """POST /api/sync with campaign structure."""
    payload = {
        "campaigns": [{
            "campaign_id": deploy_result["campaign_id"],
            "name": deploy_result["campaign_name"],
            "status": "active",
            "daily_budget": deploy_result["daily_budget"],
        }],
        "ad_groups": deploy_result["ad_groups"],
        "ads": deploy_result["ads"],
        "keywords": deploy_result["keywords"],
    }

    response = requests.post(
        f"{WORKERS_URL}/api/sync",
        json=payload,
        headers={"X-Hermes-Secret": HERMES_SYNC_SECRET},
        timeout=30,
    )
    response.raise_for_status()
```

## Todo
- [ ] Update SKILL.md with creator commands
- [ ] Create `scripts/deploy.py` — Google Ads API wrapper (campaign, ad_group, keywords, ads)
- [ ] Implement retry_with_backoff() for rate limit handling
- [ ] Implement batch processing (groups of 10)
- [ ] Create `scripts/policy_check.py` — policy screening rules
- [ ] Create `references/restricted-terms.md` — Google Ads policy reference
- [ ] Create `scripts/creator.py` — orchestrator (plan → copy → screen → approve → deploy)
- [ ] Implement budget guardrail: per-campaign `max_daily = monthly/30*2` + account total check
- [ ] Implement human approval flow (numbered selection)
- [ ] Implement ad-copy-learning.db storage (approved + rejected)
- [ ] Implement D1 sync after campaign creation
- [ ] Test: create test campaign on test account
- [ ] Verify: campaign appears in Google Ads UI

## Success Criteria
- `creator.py` reads research plan JSON → generates 10-15 ad copy variations
- Policy screening rejects variations with disallowed terms + character violations
- Human approval flow: numbered list → user selects → only selected deployed
- Budget guardrail enforced: daily_budget never exceeds monthly/30*2 (per-campaign AND account total)
- Account total check: new campaign's daily budget + existing daily budgets ≤ account cap
- Google Ads API deployment succeeds (campaign, ad groups, keywords, ads created)
- Partial failure: failed batch reported, succeeded batch preserved
- Campaign structure synced to D1 via POST /api/sync
- All generated copy saved to ad-copy-learning.db (approved + rejected)
- Campaign visible in Google Ads UI within 5 minutes

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| LLM generates policy-violating copy (C3) | Crit | policy_check.py screens BEFORE approval. Human review as final gate. |
| Budget hallucination by LLM (C1) | Crit | Budget hardcoded as constant. LLM never sets budget value. |
| API rate limit on deploy (H1) | High | Batch in groups of 10. Retry with exponential backoff (3 retries). |
| Partial deployment failure | Med | Batch rollback on error. Report succeeded/failed separately. User can retry failed batch. |
| Google Ads API version mismatch (H9) | Med | Pin google-ads-python version in requirements. Test on test account first. |
| Research plan missing required fields | Low | Validate plan JSON before processing. Error with clear message. |
| OAuth token expired during deploy | Med | google-ads-python handles refresh automatically. Monitor for auth errors. |

## Security
- OAuth credentials loaded from google-ads.env (gitignored)
- No ad copy contains PII (business marketing only)
- Sync to D1 uses X-Hermes-Secret header
- Budget guardrails cannot be overridden by any input (per-campaign + account total)

## Next Steps
- Phase 04 (monitor) — tracks campaigns created here
- Phase 06 (integration) — end-to-end test of create → monitor → dashboard flow
