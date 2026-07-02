// D1 database helpers for upserting data

export async function upsertCampaign(db, campaign) {
  await db.prepare(`
    INSERT OR REPLACE INTO campaigns (
      campaign_id, name, status, campaign_type, daily_budget, monthly_budget,
      objective, has_conversion_tracking, created_at, updated_at, last_seen_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    campaign.campaign_id,
    // Local SQLite campaigns use `niche` as the human name (no `name` col);
    // fall back so D1 always gets a displayable name (avoids D1_TYPE_ERROR on undefined).
    campaign.name || campaign.niche || null,
    campaign.status || 'active',
    campaign.campaign_type || 'search',
    campaign.daily_budget || 0,
    campaign.monthly_budget || 500.00,
    campaign.objective || 'leads',
    campaign.has_conversion_tracking !== undefined ? campaign.has_conversion_tracking : 1,
    campaign.created_at || new Date().toISOString(),
    campaign.updated_at || new Date().toISOString(),
    campaign.last_seen_at || null
  ).run();
}

export async function batchUpsertMetrics(db, metrics) {
  // Prepare the statement for better performance
  const stmt = db.prepare(`
    INSERT OR REPLACE INTO daily_metrics (
      entity_type, entity_id, date, impressions, clicks, cost, conversions, conversion_value, synced_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  // Batch all metrics
  const batch = [];
  for (const metric of metrics) {
    batch.push(
      stmt.bind(
        metric.entity_type,
        metric.entity_id,
        metric.date,
        metric.impressions || 0,
        metric.clicks || 0,
        metric.cost || 0.0,
        metric.conversions || 0,
        metric.conversion_value || 0.0,
        metric.synced_at || new Date().toISOString()
      )
    );
  }

  // Execute all statements in a batch
  await db.batch(batch);
}

export async function batchUpsertLeads(db, leads) {
  // Prepare the statement for better performance
  const stmt = db.prepare(`
    INSERT OR REPLACE INTO leads (
      campaign_id, conversion_id, source, conversion_date, conversion_value, created_at
    ) VALUES (?, ?, ?, ?, ?, ?)
  `);

  // Batch all leads
  const batch = [];
  for (const lead of leads) {
    batch.push(
      stmt.bind(
        lead.campaign_id,
        lead.conversion_id,
        lead.source || 'google_ads',
        lead.conversion_date,
        lead.conversion_value || 0.0,
        lead.created_at || new Date().toISOString()
      )
    );
  }

  // Execute all statements in a batch
  await db.batch(batch);
}

export async function batchUpsertAdGroups(db, adGroups) {
  const stmt = db.prepare(`
    INSERT OR REPLACE INTO ad_groups (
      ad_group_id, campaign_id, name, status, cpc_bid, created_at
    ) VALUES (?, ?, ?, ?, ?, ?)
  `);

  const batch = [];
  for (const adGroup of adGroups) {
    batch.push(
      stmt.bind(
        adGroup.ad_group_id,
        adGroup.campaign_id,
        adGroup.name,
        adGroup.status || 'active',
        adGroup.cpc_bid || null,
        adGroup.created_at || new Date().toISOString()
      )
    );
  }

  await db.batch(batch);
}

export async function batchUpsertAds(db, ads) {
  const stmt = db.prepare(`
    INSERT OR REPLACE INTO ads (
      ad_id, ad_group_id, campaign_id, headline_1, headline_2, headline_3,
      description_1, description_2, status, approval_status, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  const batch = [];
  for (const ad of ads) {
    batch.push(
      stmt.bind(
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
      )
    );
  }

  await db.batch(batch);
}

export async function batchUpsertKeywords(db, keywords) {
  const stmt = db.prepare(`
    INSERT OR REPLACE INTO keywords (
      keyword_id, ad_group_id, campaign_id, text, match_type, status, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
  `);

  const batch = [];
  for (const keyword of keywords) {
    batch.push(
      stmt.bind(
        keyword.keyword_id,
        keyword.ad_group_id,
        keyword.campaign_id,
        keyword.text,
        keyword.match_type || 'PHRASE',
        keyword.status || 'active',
        keyword.created_at || new Date().toISOString()
      )
    );
  }

  await db.batch(batch);
}