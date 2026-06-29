#!/usr/bin/env python3
import os
import time
from typing import Dict, List, Any, Optional
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.api_core import exceptions

BATCH_SIZE = 10


def get_client(env_file: str = "google-ads.env") -> GoogleAdsClient:
    """Load Google Ads client from environment file.

    TODO: Implement proper Google Ads client loading
    """
    print(f"[CLIENT] Loading Google Ads client from {env_file}")

    # Check if environment file exists
    if not os.path.exists(env_file):
        print(f"Warning: {env_file} not found. Using mock client.")
        return MockGoogleAdsClient()

    try:
        client = GoogleAdsClient.load_from_env(version="v17")
        print("[CLIENT] Google Ads client loaded successfully")
        return client
    except Exception as e:
        print(f"[CLIENT] Error loading Google Ads client: {e}")
        return MockGoogleAdsClient()


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
        daily_budget_micros: Daily budget in micros (1 micro = 0.000001 USD)

    Returns:
        Campaign resource name or None if failed
    """
    print(f"[CAMPAIGN] Creating campaign: {name}")

    if isinstance(client, MockGoogleAdsClient):
        print(f"[CAMPAIGN] Mock: Would create campaign '{name}' with budget ${daily_budget_micros / 1000000}")
        return f"customers/{customer_id}/campaigns/mock-campaign-123"

    try:
        # Create campaign budget
        budget_service = client.get_service("CampaignBudgetService")
        budget_operation = client.get_type("CampaignBudgetOperation")
        budget = budget_operation.create
        budget.name = f"{name} - Budget"
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
        campaign.name = name
        campaign.status = client.enums.CampaignStatusEnum.ENABLED
        campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
        campaign.bidding_strategy_type = client.enums.BiddingStrategyTypeEnum.MANUAL_CPC
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
        print(f"[ADGROUP] Mock: Would create ad group '{name}' with CPC ${cpc_bid_micros / 1000000}")
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


def create_ads(client: GoogleAdsClient, customer_id: str, ad_group_resource_name: str, ads: List[Dict[str, Any]]) -> List[str]:
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
            responsive_ad.headlines.extend([
                client.get_type("AdTextAsset",
                                text=headline,
                                pinned_field=None)
                for headline in ad_data["headlines"]
            ])
            responsive_ad.descriptions.extend([
                client.get_type("AdTextAsset",
                                text=description,
                                pinned_field=None)
                for description in ad_data["descriptions"]
            ])

            # Set final URLs and paths
            responsive_ad.final_urls.extend(["https://example.com"])
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
    """Retry function with exponential backoff for rate limit handling."""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except exceptions.TooManyRequests as e:
            if attempt == max_retries:
                raise e

            delay = base_delay * (2 ** attempt)
            print(f"[RETRY] Rate limited, waiting {delay}s (attempt {attempt + 1}/{max_retries + 1})")
            time.sleep(delay)
        except Exception as e:
            # Don't retry on other exceptions
            raise e


def deploy_full_campaign(client: GoogleAdsClient, customer_id: str, plan: Dict[str, Any], variations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deploy a complete campaign with budget, campaign, ad groups, keywords, and ads."""
    print(f"[DEPLOY] Starting full campaign deployment")

    campaign_name = f"{plan['niche']} - {plan['location']}"
    daily_budget_micros = int(plan['budget_plan']['daily_budget'] * 1000000)

    # Create campaign
    campaign_resource_name = retry_with_backoff(
        lambda: create_campaign(client, customer_id, campaign_name, daily_budget_micros)
    )

    if not campaign_resource_name:
        print("[DEPLOY] Failed to create campaign")
        return {"success": False, "error": "Campaign creation failed"}

    # Create ad group
    ad_group_name = f"{campaign_name} - Main"
    cpc_bid_micros = int(plan['budget_plan']['estimated_cpc_range'][0] * 1000000)  # Use lower estimate

    ad_group_resource_name = retry_with_backoff(
        lambda: create_ad_group(client, customer_id, campaign_resource_name, ad_group_name, cpc_bid_micros)
    )

    if not ad_group_resource_name:
        print("[DEPLOY] Failed to create ad group")
        return {"success": False, "error": "Ad group creation failed"}

    # Create keywords
    keywords = [kw["keyword"] for kw in plan.get("keywords", [])]
    keyword_resource_names = retry_with_backoff(
        lambda: create_keywords(client, customer_id, ad_group_resource_name, keywords)
    )

    # Create ads
    ad_resource_names = retry_with_backoff(
        lambda: create_ads(client, customer_id, ad_group_resource_name, variations)
    )

    result = {
        "success": True,
        "campaign_name": campaign_name,
        "campaign_resource_name": campaign_resource_name,
        "ad_group_name": ad_group_name,
        "ad_group_resource_name": ad_group_resource_name,
        "keywords_created": len(keyword_resource_names),
        "ads_created": len(ad_resource_names)
    }

    print(f"[DEPLOY] Campaign deployed successfully: {result}")
    return result