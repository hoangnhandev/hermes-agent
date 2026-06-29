# Phase 00 — Google Ads Account Setup + API Access

## Context
- Parent: [plan.md](plan.md). Depends: none (first phase).
- Prerequisites: Google account, landing page with lead form, billing method.
- Mostly guided manual work with some env file creation.
- Blocks: Phase 03 (creator skill needs API credentials).

## Overview
Create a new Google Ads account from scratch, link it to Google Cloud, obtain
OAuth 2.0 credentials and Developer Token, set up conversion tracking, and
install the Python client library on the Hermes VPS. Output = `google-ads.env`
template ready for Phase 03.

## Key Insights
- New Google Ads accounts start at **Explorer** access level. Request Basic Access
  immediately (may take 1-2 days to approve). Basic Access required for reporting
  queries in Phase 04.
- **Manual CPC** is mandatory for new accounts. Smart Bidding needs 30+ conversions
  in 30 days — not achievable on $500/mo lead-gen budget initially.
- Conversion tracking must be set up BEFORE creating campaigns. Google Ads needs
  a conversion action ID to attribute leads.
- Developer Token starts in test mode. Test mode can only manage test accounts.
  Request production access via Google Ads API Center.

## Requirements
- **Functional**: working Google Ads account with billing, OAuth credentials,
  Developer Token, conversion action created, `google-ads.env` template.
- **Non-functional**: credentials stored in env file (never committed), test
  campaign created to verify account is operational.

## Architecture
```
google-ads.env          # env template (gitignored)
Google Ads Account      # new account, Search campaigns
Google Cloud Project     # OAuth 2.0 client credentials
Google Ads API Center   # Developer Token + access level
google-ads-python       # installed on Hermes VPS
```

## Related Code Files
- **Create**: `google-ads.env` (template with all required vars)
- **Create**: `skills/research/google-ads/google-ads.env.example` (committed, no secrets)
- **Read**: `skills/research/google-ads/` (skill dir created in Phase 01)

## Interfaces

### Consumes
- Google account credentials (user provides)
- Billing method (user provides)
- Landing page URL with lead form (user provides)

### Produces
- `google-ads.env` with populated values (gitignored):
  ```
  GOOGLE_ADS_CLIENT_ID=
  GOOGLE_ADS_CLIENT_SECRET=
  GOOGLE_ADS_DEVELOPER_TOKEN=
  GOOGLE_ADS_REFRESH_TOKEN=
  GOOGLE_ADS_CUSTOMER_ID=
  GOOGLE_ADS_LOGIN_CUSTOMER_ID=
  GOOGLE_ADS_CONVERSION_ACTION_ID=
  ```

## Implementation Steps

### Step 1: Create Google Ads Account (30 min)
1. Go to https://ads.google.com → "Start now"
2. Switch to **Expert Mode** (skip the guided setup wizard)
3. Select **Search campaign** type (required to create account)
4. Set temporary campaign name: "Setup Test Campaign"
5. Set budget to **$1/day** (just to activate account)
6. Enter any URL as landing page (will be paused immediately)
7. Complete billing setup: add payment method
8. After account creation, note the **Customer ID** (format: `123-456-7890`)
9. **Pause** the test campaign immediately

### Step 2: Set Up Conversion Tracking (20 min)
1. In Google Ads UI: Tools → Conversions → New conversion action
2. Select **Website** → **Manual tagging**
3. Name: "Lead Form Submission"
4. Category: **Leads**
5. Value: **Don't use a value**
6. Counting: **Every conversion** (not "one per ad click")
7. Save → note the **Conversion Action ID**
8. Install Google Tag on landing page:
   ```html
   <!-- Google Tag (gtag.js) - Conversion Tracking -->
   <script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
   <script>
     window.dataLayer = window.dataLayer || [];
     function gtag(){dataLayer.push(arguments);}
     gtag('js', new Date());
     gtag('config', 'G-XXXXXXXXXX');
   </script>
   ```
9. Add conversion event on form submit:
   ```javascript
   gtag('event', 'conversion', {
     'send_to': 'AW-XXXXXXXXXX/YYYYYYYYYY'
   });
   ```

### Step 3: Link Google Cloud Project (15 min)
1. Go to https://console.cloud.google.com
2. Create new project (or select existing): name it `hermes-ads-copilot`
3. Enable **Google Ads API**:
   ```bash
   gcloud services enable googleads.googleapis.com
   ```
4. Note the Project ID and Project Number

### Step 4: Create OAuth 2.0 Credentials (15 min)
1. Google Cloud Console → APIs & Services → Credentials
2. Create **OAuth 2.0 Client ID**
3. Application type: **Desktop app** (for server-side Python scripts)
4. Name: `hermes-ads-copilot`
5. Save → note **Client ID** and **Client Secret**
6. Download JSON credentials file (optional backup)

### Step 5: Generate Developer Token (15 min)
1. Go to https://ads.google.com/aw/api-center
2. Generate **Developer Token**
3. Note the token (starts in **Test** mode)
4. Request **Basic Access**:
   - Click "Request Basic Access"
   - Fill in: purpose ("Manage lead gen campaigns via automation"),
     estimated monthly operations (~10,000), estimated daily operations (~500)
   - Accept terms
   - **May take 1-2 business days** — Phase 03 can proceed in test mode for now

### Step 6: Authorize + Store Refresh Token (30 min)
1. SSH to Hermes VPS
2. Install google-ads-python:
   ```bash
   # DO NOT use global pip — use venv
   cd ~/hermes-agent
   python3 -m venv .venv-google-ads
   source .venv-google-ads/bin/activate
   pip install google-ads
   pip freeze > google-ads-requirements.txt
   ```
3. Create auth script to get refresh token:
   ```python
   # scripts/auth.py (temporary, deleted after use)
   from google.ads.googleads.oauth2 import OfflineCredentials

   credentials = OfflineCredentials(
       client_id="YOUR_CLIENT_ID",
       client_secret="YOUR_CLIENT_SECRET",
       developer_token="YOUR_DEVELOPER_TOKEN",
       login_customer_id="YOUR_CUSTOMER_ID",  # no dashes
   )
   credentials.fetch_token()  # opens browser for consent
   print(credentials.refresh_token)
   ```
4. Run script → complete OAuth consent in browser → copy refresh token
5. Delete `scripts/auth.py` after obtaining refresh token

### Step 7: Create Test Campaign (15 min)
1. In Google Ads UI → Campaigns → New
2. Campaign type: **Search**
3. Name: "Test Campaign - Delete After Setup"
4. Budget: **$1/day**
5. Bidding: **Manual CPC** (default)
6. Targeting: any single keyword (e.g. "test keyword")
7. One ad group, one ad (placeholder text)
8. Launch → verify campaign is "Eligible"
9. After verification, **pause** this campaign

### Step 8: Create google-ads.env Template (10 min)
1. Create `skills/research/google-ads/google-ads.env.example`:
   ```bash
   # Google Ads API Configuration
   GOOGLE_ADS_CLIENT_ID=your_client_id.apps.googleusercontent.com
   GOOGLE_ADS_CLIENT_SECRET=your_client_secret
   GOOGLE_ADS_DEVELOPER_TOKEN=your_developer_token
   GOOGLE_ADS_REFRESH_TOKEN=your_refresh_token
   GOOGLE_ADS_CUSTOMER_ID=1234567890          # no dashes
   GOOGLE_ADS_LOGIN_CUSTOMER_ID=1234567890    # no dashes, same as above for direct access

   # Conversion Tracking
   GOOGLE_ADS_CONVERSION_ACTION_ID=1234567890

   # Google Cloud Project
   GOOGLE_CLOUD_PROJECT_ID=hermes-ads-copilot

   # Budget Guardrails (never change these without code review)
   MONTHLY_BUDGET=500
   MAX_DAILY_MULTIPLIER=2
   ```
2. Create actual `google-ads.env` with real values (gitignored)
3. Add `google-ads.env` to `.gitignore`

## Todo
- [ ] Create Google Ads account (Expert Mode)
- [ ] Set up billing + note Customer ID
- [ ] Create conversion action + install Google Tag on landing page
- [ ] Create Google Cloud project + enable Google Ads API
- [ ] Create OAuth 2.0 Desktop credentials
- [ ] Generate Developer Token
- [ ] Request Basic Access (may take 1-2 days)
- [ ] Install google-ads-python on Hermes VPS (venv)
- [ ] Obtain refresh token via OAuth flow
- [ ] Create + pause test campaign
- [ ] Create google-ads.env + google-ads.env.example
- [ ] Add google-ads.env to .gitignore
- [ ] Verify: run `google-ads` CLI against test account

## Success Criteria
- Google Ads account is active with Customer ID recorded
- Conversion action exists with ID recorded
- OAuth credentials generated and refresh token obtained
- Developer Token generated (test or basic access)
- `google-ads.py` can query test campaign:
  ```bash
  python3 -c "
  from google.ads.googleads.client import GoogleAdsClient
  client = GoogleAdsClient.load_from_env('google-ads.env')
  ga_service = client.get_service('GoogleAdsService')
  query = 'SELECT campaign.id, campaign.name FROM campaign'
  results = ga_service.search(query)
  for row in results:
      print(f'Campaign: {row.campaign.name} (ID: {row.campaign.id})')
  "
  ```
- google-ads.env.example committed, google-ads.env gitignored

## Risk Assessment
| Risk | Sev | Mitigation |
|---|---|---|
| Basic Access denied or delayed | High | Start in Test mode for dev. Phase 03 works with test accounts. Prod access can arrive later. |
| Developer Token stuck in test mode | Med | Test mode manages test accounts — sufficient for development. |
| OAuth refresh token expires | Med | OfflineCredentials (access_type=offline) → long-lived. Monitor via test queries. |
| Landing page has no lead form yet | Med | Conversion tracking still set up. Leads = 0 until form exists. Not blocking. |
| Account suspended during setup | Low | Unlikely for new account with legitimate business info. Appeal process exists. |

## Security
- Never commit `google-ads.env` to git
- Refresh token grants full API access to the account
- Developer Token is account-scoped — protect as secret
- OAuth credentials restricted to Desktop app (no web redirect URI)

## Next Steps
- Phase 01 (research skill) can start in parallel — no API needed
- Phase 03 (creator skill) blocked until OAuth credentials + Developer Token ready
- If Basic Access delayed: Phase 03 proceeds in test mode, Phase 04 switches to prod when granted
