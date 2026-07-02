import { upsertCampaign, batchUpsertMetrics, batchUpsertLeads } from './db-helpers.js';

// Simple in-memory rate limiting (1 request per minute)
const rateLimitMap = new Map();

// Rate limiting middleware
function checkRateLimit(request) {
  const ip = request.headers.get('cf-connecting-ip') || 'unknown';
  const now = Date.now();
  const lastRequest = rateLimitMap.get(ip) || 0;

  if (now - lastRequest < 60000) { // 1 minute
    return false;
  }

  rateLimitMap.set(ip, now);
  return true;
}

export async function handleSync(request, env) {
  // Check X-Hermes-Secret header
  const syncSecret = request.headers.get('X-Hermes-Secret');
  if (!syncSecret || syncSecret !== env.HERMES_SYNC_SECRET) {
    return new Response(JSON.stringify({ error: 'Invalid sync secret' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // Rate limiting
  if (!checkRateLimit(request)) {
    return new Response(JSON.stringify({ error: 'Rate limit exceeded' }), {
      status: 429,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  try {
    const body = await request.json();
    const { metrics, leads, campaigns, ad_groups, ads, keywords, anomalies } = body;

    const syncedCounts = {
      metrics: 0,
      leads: 0,
      campaigns: 0,
      ad_groups: 0,
      ads: 0,
      keywords: 0,
      anomalies: 0
    };

    // Process campaigns
    if (campaigns && campaigns.length > 0) {
      for (const campaign of campaigns) {
        await upsertCampaign(env.DB, campaign);
        syncedCounts.campaigns++;
      }
    }

    // Process ad groups
    if (ad_groups && ad_groups.length > 0) {
      for (const adGroup of ad_groups) {
        await env.DB.prepare(`
          INSERT OR REPLACE INTO ad_groups (
            ad_group_id, campaign_id, name, status, cpc_bid, created_at
          ) VALUES (?, ?, ?, ?, ?, ?)
        `).bind(
          adGroup.ad_group_id,
          adGroup.campaign_id,
          adGroup.name,
          adGroup.status || 'active',
          adGroup.cpc_bid || null,
          adGroup.created_at || new Date().toISOString()
        ).run();
        syncedCounts.ad_groups++;
      }
    }

    // Process ads
    if (ads && ads.length > 0) {
      for (const ad of ads) {
        await env.DB.prepare(`
          INSERT OR REPLACE INTO ads (
            ad_id, ad_group_id, campaign_id, headline_1, headline_2, headline_3,
            description_1, description_2, status, approval_status, created_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).bind(
          ad.ad_id,
          ad.ad_group_id,
          ad.campaign_id,
          ad.headline_1 || null,
          ad.headline_2 || null,
          ad.headline_3 || null,
          ad.description_1 || null,
          ad.description_2 || null,
          ad.status || 'active',
          ad.approval_status || 'approved',
          ad.created_at || new Date().toISOString()
        ).run();
        syncedCounts.ads++;
      }
    }

    // Process keywords
    if (keywords && keywords.length > 0) {
      for (const keyword of keywords) {
        await env.DB.prepare(`
          INSERT OR REPLACE INTO keywords (
            keyword_id, ad_group_id, campaign_id, text, match_type, status, created_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?)
        `).bind(
          keyword.keyword_id,
          keyword.ad_group_id,
          keyword.campaign_id,
          keyword.text,
          keyword.match_type || 'PHRASE',
          keyword.status || 'active',
          keyword.created_at || new Date().toISOString()
        ).run();
        syncedCounts.keywords++;
      }
    }

    // Process anomalies (wire 5). INSERT OR IGNORE respects the
    // (detected_at, entity_id, anomaly_type) PK so re-syncs don't duplicate.
    // Per-row try/catch (review M2): a single bad anomaly insert (transient D1
    // error / schema drift) must NOT fail the whole POST and block the metrics
    // batch that runs next — isolate + continue.
    if (anomalies && anomalies.length > 0) {
      for (const anomaly of anomalies) {
        try {
          await env.DB.prepare(`
            INSERT OR IGNORE INTO anomalies (
              detected_at, anomaly_type, entity_id, entity_name,
              metric_name, current_value, baseline_value, change_pct, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
          `).bind(
            anomaly.detected_at || new Date().toISOString(),
            anomaly.anomaly_type,
            anomaly.entity_id || null,
            anomaly.entity_name || null,
            anomaly.metric_name,
            anomaly.current_value ?? null,
            anomaly.baseline_value ?? null,
            anomaly.change_pct ?? null,
            new Date().toISOString()
          ).run();
          syncedCounts.anomalies++;
        } catch (e) {
          console.error('Anomaly insert failed (continuing):', e?.message || e);
        }
      }
    }

    // Batch process metrics
    if (metrics && metrics.length > 0) {
      await batchUpsertMetrics(env.DB, metrics);
      syncedCounts.metrics = metrics.length;
    }

    // Batch process leads
    if (leads && leads.length > 0) {
      await batchUpsertLeads(env.DB, leads);
      syncedCounts.leads = leads.length;
    }

    return new Response(JSON.stringify({
      success: true,
      synced: syncedCounts
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Sync error:', error);
    return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}