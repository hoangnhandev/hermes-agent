#!/usr/bin/env python3
import os
import time
import uuid
from typing import Dict, List, Any, Optional

# google-ads is optional at import time so --mock dry-runs work WITHOUT the
# lib installed (true credential/lib-free dry-run). get_client() enforces
# availability for LIVE (non-mock) deploys. Review found: previously the
# top-level import made --mock crash in any env lacking google-ads.
try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    GOOGLEADS_AVAILABLE = True
except ImportError:
    GOOGLEADS_AVAILABLE = False
    GoogleAdsClient = None
    GoogleAdsException = Exception  # broad fallback; mock path returns early
from _env import load_google_ads_env
from _budget_calc import to_micros_from_vnd, from_micros

BATCH_SIZE = 10


def get_client(env_file: str = "google-ads.env", allow_mock: bool = False) -> GoogleAdsClient:
    """Load Google Ads client from environment file.

    Fails HARD on missing/broken credentials unless allow_mock=True (explicit
    --mock dry-run). Never silently mock — a skill that spends money must not
    pretend to deploy when it can't. (Fixes H1: silent-mock trust violation.)
    """
    if not GOOGLEADS_AVAILABLE:
        if allow_mock:
            print("[CLIENT] google-ads lib not installed — MOCK mode (--mock)")
            return MockGoogleAdsClient()
        raise RuntimeError(
            "google-ads library not installed. Install it (`pip install google-ads`) "
            "for a live deploy, or pass --mock for a dry-run.")
    if not os.path.exists(env_file):
        if allow_mock:
            print(f"[CLIENT] {env_file} not found — MOCK mode (--mock)")
            return MockGoogleAdsClient()
        raise RuntimeError(
            f"{env_file} not found. Set Google Ads credentials (see google-ads.env.example) "
            "or pass --mock for a dry-run. Refusing to deploy without real credentials.")

    try:
        load_google_ads_env(env_file)  # populate os.environ from google-ads.env
        client = GoogleAdsClient.load_from_env(version=os.getenv("GOOGLE_ADS_API_VERSION", "v21"))
        print("[CLIENT] Google Ads client loaded successfully")
        return client
    except Exception as e:
        if allow_mock:
            print(f"[CLIENT] load failed ({e}) — MOCK mode (--mock)")
            return MockGoogleAdsClient()
        raise RuntimeError(
            f"Google Ads client load failed: {e}. Fix credentials in {env_file} or use --mock.")


class MockGoogleAdsClient:
    """Mock client for development without API credentials."""
    def __init__(self):
        self.customer_id = "1234567890"


def create_campaign(client: GoogleAdsClient, customer_id: str, name: str, daily_budget_micros: int) -> Optional[str]:
    """Create a Search campaign with Manual CPC bidding.

    Args:
        client: Google Ads client
        customer_id: Google Ads customer ID
        name: Campaign name
        daily_budget_micros: Daily budget in micros (1 micro = 1e-6 of the
            account-currency unit; VND by default — see ACCOUNT_CURRENCY)

    Returns:
        Campaign resource name or None if failed
    """
    # Budget names must be unique per account. Append a short uuid suffix so a
    # re-deploy (or an orphan budget left by a failed prior attempt) doesn't
    # collide with DUPLICATE_NAME. Campaign names may repeat, but suffix them
    # too so multiple deploys are distinguishable in the UI.
    suffix = uuid.uuid4().hex[:8]
    unique_name = f"{name} {suffix}"
    print(f"[CAMPAIGN] Creating campaign: {unique_name}")

    if isinstance(client, MockGoogleAdsClient):
        print(f"[CAMPAIGN] Mock: Would create campaign '{unique_name}' with budget "
              f"{from_micros(daily_budget_micros):,.0f} VND")
        return f"customers/{customer_id}/campaigns/mock-campaign-123"

    try:
        # Create campaign budget
        budget_service = client.get_service("CampaignBudgetService")
        budget_operation = client.get_type("CampaignBudgetOperation")
        budget = budget_operation.create
        budget.name = f"{unique_name} - Budget"
        budget.amount_micros = daily_budget_micros
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD

        budget_response = budget_service.mutate_campaign_budgets(
            customer_id=customer_id,
            operations=[budget_operation]
        )
        budget_resource_name = budget_response.results[0].resource_name

        # Create campaign
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.create
        campaign.name = unique_name
        campaign.status = client.enums.CampaignStatusEnum.ENABLED
        campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
        # Set the inline Manual CPC strategy. Setting bidding_strategy_type (enum)
        # alone does NOT populate the required campaign_bidding_strategy oneof —
        # the API rejects with REQUIRED field_error on campaign_bidding_strategy.
        # Setting manual_cpc populates the oneof AND infers the type.
        campaign.manual_cpc = client.get_type("ManualCpc")
        campaign.manual_cpc.enhanced_cpc_enabled = True
        campaign.campaign_budget = budget_resource_name

        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation]
        )

        campaign_resource_name = campaign_response.results[0].resource_name
        print(f"[CAMPAIGN] Created campaign: {campaign_resource_name}")
        return campaign_resource_name

    except GoogleAdsException as ex:
        print(f"[CAMPAIGN] Google Ads exception: {ex}")
        return None
    except Exception as e:
        print(f"[CAMPAIGN] Error: {e}")
        return None


def create_ad_group(client: GoogleAdsClient, customer_id: str, campaign_resource_name: str, name: str, cpc_bid_micros: int) -> Optional[str]:
    """Create an ad group within a campaign.

    Args:
        client: Google Ads client
        customer_id: Google Ads customer ID
        campaign_resource_name: Campaign resource name
        name: Ad group name
        cpc_bid_micros: CPC bid in micros

    Returns:
        Ad group resource name or None if failed
    """
    print(f"[ADGROUP] Creating ad group: {name}")

    if isinstance(client, MockGoogleAdsClient):
        print(f"[ADGROUP] Mock: Would create ad group '{name}' with CPC "
              f"{from_micros(cpc_bid_micros):,.0f} VND")
        return f"customers/{customer_id}/adGroups/mock-adgroup-123"

    try:
        ad_group_service = client.get_service("AdGroupService")
        ad_group_operation = client.get_type("AdGroupOperation")
        ad_group = ad_group_operation.create
        ad_group.name = name
        ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
        ad_group.campaign = campaign_resource_name
        ad_group.type = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
        ad_group.cpc_bid_micros = cpc_bid_micros

        ad_group_response = ad_group_service.mutate_ad_groups(
            customer_id=customer_id,
            operations=[ad_group_operation]
        )

        ad_group_resource_name = ad_group_response.results[0].resource_name
        print(f"[ADGROUP] Created ad group: {ad_group_resource_name}")
        return ad_group_resource_name

    except GoogleAdsException as ex:
        print(f"[ADGROUP] Google Ads exception: {ex}")
        return None
    except Exception as e:
        print(f"[ADGROUP] Error: {e}")
        return None


def create_keywords(client: GoogleAdsClient, customer_id: str, ad_group_resource_name: str, keywords: List[str]) -> List[str]:
    """Batch-create keywords in an ad group.

    Args:
        client: Google Ads client
        customer_id: Google Ads customer ID
        ad_group_resource_name: Ad group resource name
        keywords: List of keyword texts

    Returns:
        List of created keyword resource names
    """
    print(f"[KEYWORDS] Creating {len(keywords)} keywords in batches of {BATCH_SIZE}")

    if isinstance(client, MockGoogleAdsClient):
        print(f"[KEYWORDS] Mock: Would create keywords: {', '.join(keywords[:3])}...")
        return [f"customers/{customer_id}/adGroupCriterion/mock-keyword-{i}" for i in range(len(keywords))]

    created_keywords = []

    for i in range(0, len(keywords), BATCH_SIZE):
        batch = keywords[i:i + BATCH_SIZE]
        print(f"[KEYWORDS] Processing batch {i//BATCH_SIZE + 1}: {len(batch)} keywords")

        operations = []
        for keyword_text in batch:
            keyword_operation = client.get_type("AdGroupCriterionOperation")
            keyword = keyword_operation.create
            keyword.ad_group = ad_group_resource_name
            keyword.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
            keyword.keyword.text = keyword_text
            keyword.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE

            operations.append(keyword_operation)

        try:
            keyword_service = client.get_service("AdGroupCriterionService")
            keyword_response = keyword_service.mutate_ad_group_criteria(
                customer_id=customer_id,
                operations=operations
            )

            batch_keywords = [result.resource_name for result in keyword_response.results]
            created_keywords.extend(batch_keywords)
            print(f"[KEYWORDS] Created {len(batch_keywords)} keywords in batch {i//BATCH_SIZE + 1}")

        except GoogleAdsException as ex:
            print(f"[KEYWORDS] Google Ads exception in batch {i//BATCH_SIZE + 1}: {ex}")
            # Continue with next batch
            continue
        except Exception as e:
            print(f"[KEYWORDS] Error in batch {i//BATCH_SIZE + 1}: {e}")
            continue

    print(f"[KEYWORDS] Total keywords created: {len(created_keywords)}/{len(keywords)}")
    return created_keywords


def create_negative_keywords(client: GoogleAdsClient, customer_id: str,
                             campaign_resource_name: str, negatives: List[str]) -> List[str]:
    """Add campaign-level negative keywords (wire 6a).

    Negatives BLOCK matching queries → cut wasted spend on low-intent traffic
    (e.g. "vf3 cũ", "review vf3", "tin tức vf3"). Campaign-level is the simplest
    scope (KISS). Best-effort + non-fatal: a failure logs and returns [] —
    negatives are a spend optimization, not a deploy gate, so a bad negative
    must never roll back an otherwise-good campaign.
    """
    if not negatives:
        print("[NEGATIVES] No negative keywords to add")
        return []

    print(f"[NEGATIVES] Adding {len(negatives)} campaign-level negative keywords")

    if isinstance(client, MockGoogleAdsClient):
        print(f"[NEGATIVES] Mock: Would add negatives: {', '.join(negatives[:5])}")
        return [f"customers/{customer_id}/campaignCriteria/mock-negative-{i}"
                for i in range(len(negatives))]

    operations = []
    for text in negatives:
        op = client.get_type("CampaignCriterionOperation")
        cc = op.create
        cc.campaign = campaign_resource_name
        cc.negative = True
        cc.keyword.text = text
        cc.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
        operations.append(op)

    try:
        service = client.get_service("CampaignCriterionService")
        response = service.mutate_campaign_criteria(
            customer_id=customer_id, operations=operations
        )
        created = [r.resource_name for r in response.results]
        print(f"[NEGATIVES] Created {len(created)} negative keywords: {', '.join(negatives[:5])}")
        return created
    except GoogleAdsException as ex:
        print(f"[NEGATIVES] Google Ads exception (non-fatal): {ex}")
        return []
    except Exception as e:
        print(f"[NEGATIVES] Error (non-fatal): {e}")
        return []


def create_ads(client: GoogleAdsClient, customer_id: str, ad_group_resource_name: str, ads: List[Dict[str, Any]], final_url: str = "https://example.com") -> List[str]:
    """Batch-create responsive search ads in an ad group.

    Args:
        client: Google Ads client
        customer_id: Google Ads customer ID
        ad_group_resource_name: Ad group resource name
        ads: List of ad variations with headlines, descriptions, paths

    Returns:
        List of created ad resource names
    """
    print(f"[ADS] Creating {len(ads)} responsive search ads in batches of {BATCH_SIZE}")

    if isinstance(client, MockGoogleAdsClient):
        print(f"[ADS] Mock: Would create ads for {len(ads)} variations")
        return [f"customers/{customer_id}/adGroupAd/mock-ad-{i}" for i in range(len(ads))]

    created_ads = []

    for i in range(0, len(ads), BATCH_SIZE):
        batch = ads[i:i + BATCH_SIZE]
        print(f"[ADS] Processing batch {i//BATCH_SIZE + 1}: {len(batch)} ads")

        operations = []
        for ad_data in batch:
            ad_operation = client.get_type("AdGroupAdOperation")
            ad = ad_operation.create
            ad.ad_group = ad_group_resource_name
            ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

            # Create responsive search ad
            responsive_ad = ad.ad.responsive_search_ad
            for headline in ad_data["headlines"]:
                asset = client.get_type("AdTextAsset")
                asset.text = headline
                responsive_ad.headlines.append(asset)
            for description in ad_data["descriptions"]:
                asset = client.get_type("AdTextAsset")
                asset.text = description
                responsive_ad.descriptions.append(asset)

            # Set final URLs and paths
            responsive_ad.final_urls.extend([final_url])
            if ad_data.get("path1"):
                responsive_ad.path1 = ad_data["path1"]
            if ad_data.get("path2"):
                responsive_ad.path2 = ad_data["path2"]

            operations.append(ad_operation)

        try:
            ad_service = client.get_service("AdGroupAdService")
            ad_response = ad_service.mutate_ad_group_ads(
                customer_id=customer_id,
                operations=operations
            )

            batch_ads = [result.resource_name for result in ad_response.results]
            created_ads.extend(batch_ads)
            print(f"[ADS] Created {len(batch_ads)} ads in batch {i//BATCH_SIZE + 1}")

        except GoogleAdsException as ex:
            print(f"[ADS] Google Ads exception in batch {i//BATCH_SIZE + 1}: {ex}")
            # Continue with next batch
            continue
        except Exception as e:
            print(f"[ADS] Error in batch {i//BATCH_SIZE + 1}: {e}")
            continue

    print(f"[ADS] Total ads created: {len(created_ads)}/{len(ads)}")
    return created_ads


def retry_with_backoff(func, max_retries: int = 3, base_delay: float = 1.0):
    """Retry on Google Ads rate-limit (RESOURCE_EXHAUSTED) with backoff.

    Fixes H3: google-ads-python raises GoogleAdsException (wrapping grpc errors)
    for rate limits, NOT google.api_core.exceptions.TooManyRequests. The old
    code never retried because it caught the wrong exception type.

    NB: only RESOURCE_EXHAUSTED is retried — the server throttled the request
    *before* applying it, so retrying these (non-idempotent) creates does not
    double-create. Transient network errors (where the op may have succeeded
    server-side but the reply was lost) are intentionally NOT retried here,
    which avoids duplicate campaigns on partial failure.
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except GoogleAdsException as ex:
            # Rate-limit = RESOURCE_EXHAUSTED error code; retry only on that.
            rate_limit = any(
                str(getattr(err.code(), "name", "")).upper() == "RESOURCE_EXHAUSTED"
                for err in (ex.errors or [])
            )
            if attempt == max_retries or not rate_limit:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"[RETRY] Rate limited, waiting {delay}s "
                  f"(attempt {attempt + 1}/{max_retries + 1})")
            time.sleep(delay)
        except Exception:
            raise  # don't retry non-rate-limit errors


def _pause_campaign(client, customer_id: str, campaign_resource_name: str) -> bool:
    """Pause a campaign so it stops spending (rollback on partial-deploy failure).

    Safer than remove: human can inspect/fix the orphan. Best-effort — logs loudly
    on failure so it is never silently left spending. (Fixes H2: orphan campaign
    with budget but no ads still spends money.)
    """
    if isinstance(client, MockGoogleAdsClient):
        print(f"[ROLLBACK] Mock: would pause orphan {campaign_resource_name}")
        return True
    try:
        service = client.get_service("CampaignService")
        op = client.get_type("CampaignOperation")
        op.update.resource_name = campaign_resource_name
        op.update.status = client.enums.CampaignStatusEnum.PAUSED
        fm = client.get_type("FieldMask")
        fm.paths.append("status")
        op.update_mask.CopyFrom(fm)
        service.mutate_campaigns(customer_id=customer_id, operations=[op])
        print(f"[ROLLBACK] Paused orphan campaign {campaign_resource_name} "
              f"(no ads → would have spent for nothing)")
        return True
    except Exception as e:
        print(f"[ROLLBACK] ⚠️⚠️ Could NOT pause {campaign_resource_name}: {e}\n"
              f"        → MANUAL CLEANUP NEEDED in Google Ads UI to stop spend!")
        return False


def deploy_full_campaign(client: GoogleAdsClient, customer_id: str, plan: Dict[str, Any], variations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deploy a complete campaign with budget, campaign, ad groups, keywords, and ads."""
    print(f"[DEPLOY] Starting full campaign deployment")

    campaign_name = f"{plan['niche']} - {plan['location']}"
    daily_budget_micros = to_micros_from_vnd(plan['budget_plan']['daily_budget'])

    # M1 guard: block example.com landing URL on a REAL client (mock OK).
    final_url = os.getenv("GOOGLE_ADS_FINAL_URL", "https://example.com")
    if "example.com" in final_url and not isinstance(client, MockGoogleAdsClient):
        return {"success": False,
                "error": "GOOGLE_ADS_FINAL_URL is example.com — set a real landing "
                         "URL in google-ads.env before live deploy (ads would point nowhere)."}

    # M2 guard: empty keywords → campaign can't match anything → wasted spend.
    keywords = [kw["keyword"] for kw in plan.get("keywords", []) if kw.get("keyword")]
    if not keywords:
        return {"success": False,
                "error": "plan has no keywords — research output missing keyword_seeds "
                         "(branded/non_branded/intent). Nothing to bid on."}
    print(f"[DEPLOY] {len(keywords)} keywords, final_url={final_url}")

    # Create campaign
    campaign_resource_name = retry_with_backoff(
        lambda: create_campaign(client, customer_id, campaign_name, daily_budget_micros)
    )

    if not campaign_resource_name:
        print("[DEPLOY] Failed to create campaign")
        return {"success": False, "error": "Campaign creation failed"}

    # Create ad group
    ad_group_name = f"{campaign_name} - Main"
    cpc_bid_micros = to_micros_from_vnd(plan['budget_plan']['estimated_cpc_range'][0])  # lower estimate

    ad_group_resource_name = retry_with_backoff(
        lambda: create_ad_group(client, customer_id, campaign_resource_name, ad_group_name, cpc_bid_micros)
    )

    if not ad_group_resource_name:
        print("[DEPLOY] Failed to create ad group — rolling back "
              "(pause campaign to stop orphan spend)")
        _pause_campaign(client, customer_id, campaign_resource_name)
        return {"success": False,
                "error": "Ad group creation failed (campaign paused — no orphan spend)"}

    # Create keywords (keywords validated above in M2 guard)
    keyword_resource_names = retry_with_backoff(
        lambda: create_keywords(client, customer_id, ad_group_resource_name, keywords)
    )
    if not keyword_resource_names:
        print("[DEPLOY] All keyword batches failed — rolling back "
              "(pause campaign: no keywords = nothing to bid on)")
        _pause_campaign(client, customer_id, campaign_resource_name)
        return {"success": False,
                "error": "Keyword creation failed for all batches (campaign paused — no orphan)"}

    # Create negative keywords (wire 6a) — best-effort, non-fatal. Failures are
    # caught inside create_negative_keywords (log + return []), so a bad negative
    # never blocks the campaign from serving. Negatives block low-intent queries
    # and reduce wasted spend.
    negatives = plan.get("negatives", []) or []
    negative_resource_names = create_negative_keywords(
        client, customer_id, campaign_resource_name, negatives
    )

    # Create ads (final_url from env; guarded against example.com above)
    ad_resource_names = retry_with_backoff(
        lambda: create_ads(client, customer_id, ad_group_resource_name, variations, final_url)
    )
    if not ad_resource_names:
        print("[DEPLOY] All ad batches failed — rolling back "
              "(pause campaign: an ad group with no ads serves nothing)")
        _pause_campaign(client, customer_id, campaign_resource_name)
        return {"success": False,
                "error": "Ad creation failed for all batches (campaign paused — no orphan)"}

    result = {
        "success": True,
        "campaign_name": campaign_name,
        "campaign_resource_name": campaign_resource_name,
        "ad_group_name": ad_group_name,
        "ad_group_resource_name": ad_group_resource_name,
        "keywords_created": len(keyword_resource_names),
        "negatives_created": len(negative_resource_names),
        "ads_created": len(ad_resource_names)
    }

    print(f"[DEPLOY] Campaign deployed successfully: {result}")
    return result