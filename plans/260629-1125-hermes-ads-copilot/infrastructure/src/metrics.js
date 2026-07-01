// /api/metrics — Overview tab data.
// Return shape ALIGNED to the dashboard frontend contract (renderOverview +
// renderPerCampaignTable + renderPerformanceTrend + renderCampaignComparison +
// renderTopKeywordsTable). Previously returned `kpis` (frontend read `account`),
// a trend of daily aggregates (frontend read per-campaign {date,campaign,metric_value}),
// and campaigns missing name/status/objective/pacing — all silently empty.
export async function handleMetrics(request, env) {
  try {
    const url = new URL(request.url);
    const dateFrom = url.searchParams.get('date_from');
    const dateTo = url.searchParams.get('date_to');
    const campaignId = url.searchParams.get('campaign_id');

    // Per-campaign metrics over the (optional) date range, plus the campaign
    // fields the per-campaign table renders (name/status/objective) and a
    // month-to-date cost for the pacing column (conditional SUM so it is
    // independent of the date filter — pacing is always a monthly concept).
    let query = `
      SELECT
        c.campaign_id,
        c.name as campaign_name,
        c.status,
        c.objective,
        c.daily_budget,
        c.monthly_budget,
        c.has_conversion_tracking,
        COALESCE(SUM(dm.impressions), 0) as impressions,
        COALESCE(SUM(dm.clicks), 0) as clicks,
        COALESCE(SUM(dm.cost), 0) as cost,
        COALESCE(SUM(dm.conversions), 0) as conversions,
        COALESCE(SUM(dm.conversion_value), 0) as conversion_value,
        COALESCE(SUM(CASE WHEN dm.date >= date('now','start of month') THEN dm.cost ELSE 0 END), 0) as mtd_cost
      FROM campaigns c
      LEFT JOIN daily_metrics dm ON c.campaign_id = dm.entity_id
        AND dm.entity_type = 'campaign'
    `;

    const queryParams = [];

    if (dateFrom || dateTo) {
      query += ' AND';
      if (dateFrom && dateTo) {
        query += ' dm.date BETWEEN ? AND ?';
        queryParams.push(dateFrom, dateTo);
      } else if (dateFrom) {
        query += ' dm.date >= ?';
        queryParams.push(dateFrom);
      } else {
        query += ' dm.date <= ?';
        queryParams.push(dateTo);
      }
    }

    if (campaignId) {
      query += ' AND c.campaign_id = ?';
      queryParams.push(campaignId);
    }

    query += ' GROUP BY c.campaign_id, c.name, c.status, c.objective, c.daily_budget, c.monthly_budget, c.has_conversion_tracking';

    const campaignsResult = await env.DB.prepare(query).bind(...queryParams).all();

    // Map each campaign to the field set renderPerCampaignTable reads:
    // name, status, objective, impressions, clicks, cpc, conversions, cost
    // (for cpl), pacing (%). ctr/cpl kept for completeness.
    const campaigns = campaignsResult.results.map(campaign => {
      const ctr = campaign.clicks > 0 ? (campaign.clicks / campaign.impressions) * 100 : 0;
      const cpc = campaign.clicks > 0 ? campaign.cost / campaign.clicks : 0;
      const cpl = campaign.conversions > 0 ? campaign.cost / campaign.conversions : null;
      // Pacing = month-to-date spend vs monthly budget (0 if no monthly budget).
      const pacing = campaign.monthly_budget > 0
        ? (campaign.mtd_cost / campaign.monthly_budget) * 100
        : 0;

      return {
        campaign_id: campaign.campaign_id,
        name: campaign.campaign_name,
        status: campaign.status,
        objective: campaign.objective,
        impressions: campaign.impressions,
        clicks: campaign.clicks,
        cost: campaign.cost,
        conversions: campaign.conversions,
        conversion_value: campaign.conversion_value,
        ctr: parseFloat(ctr.toFixed(2)),
        cpc: parseFloat(cpc.toFixed(2)),
        cpl: cpl ? parseFloat(cpl.toFixed(2)) : null,
        pacing: parseFloat(pacing.toFixed(1))
      };
    });

    // Account-level totals (frontend reads data.account.*).
    const accountTotals = campaigns.reduce((acc, c) => {
      acc.impressions += c.impressions;
      acc.clicks += c.clicks;
      acc.cost += c.cost;
      acc.conversions += c.conversions;
      acc.conversion_value += c.conversion_value;
      return acc;
    }, { impressions: 0, clicks: 0, cost: 0, conversions: 0, conversion_value: 0 });

    const account = {
      impressions: accountTotals.impressions,
      clicks: accountTotals.clicks,
      cost: accountTotals.cost,
      conversions: accountTotals.conversions,
      conversion_value: accountTotals.conversion_value,
      ctr: accountTotals.clicks > 0 ? parseFloat((accountTotals.clicks / accountTotals.impressions * 100).toFixed(2)) : 0,
      cpc: accountTotals.clicks > 0 ? parseFloat((accountTotals.cost / accountTotals.clicks).toFixed(2)) : 0,
      cpl: accountTotals.conversions > 0 ? parseFloat((accountTotals.cost / accountTotals.conversions).toFixed(2)) : null
    };

    // Performance trend: per-campaign daily series. renderPerformanceTrend reads
    // {date, campaign, metric_value} and draws one line per campaign.
    // metric_value = clicks (the most stable activity signal; conversions are
    // sparse early on). y-axis labelled "Value" in the chart.
    const trendQuery = `
      SELECT
        dm.date,
        c.name as campaign,
        SUM(dm.clicks) as metric_value
      FROM daily_metrics dm
      JOIN campaigns c ON dm.entity_id = c.campaign_id
      WHERE dm.entity_type = 'campaign'
        AND dm.date >= date('now', '-30 days')
      GROUP BY dm.date, c.name
      ORDER BY dm.date
    `;
    const trendResult = await env.DB.prepare(trendQuery).all();
    const trend = trendResult.results.map(row => ({
      date: row.date,
      campaign: row.campaign,
      metric_value: row.metric_value
    }));

    // Top keywords: renderTopKeywordsTable reads text/impressions/clicks/cpc/
    // conversions. Added SUM(conversions) (was missing → conversions column empty).
    const topKeywordsQuery = `
      SELECT
        k.text,
        k.campaign_id,
        c.name as campaign_name,
        COALESCE(SUM(dm.impressions), 0) as impressions,
        COALESCE(SUM(dm.clicks), 0) as clicks,
        COALESCE(SUM(dm.cost), 0) as cost,
        COALESCE(SUM(dm.conversions), 0) as conversions
      FROM keywords k
      LEFT JOIN daily_metrics dm ON k.keyword_id = dm.entity_id
        AND dm.entity_type = 'keyword'
      LEFT JOIN campaigns c ON k.campaign_id = c.campaign_id
      GROUP BY k.text, k.campaign_id, c.name
      ORDER BY SUM(dm.clicks) DESC
      LIMIT 10
    `;
    const topKeywordsResult = await env.DB.prepare(topKeywordsQuery).all();
    const top_keywords = topKeywordsResult.results.map(keyword => ({
      text: keyword.text,
      campaign_id: keyword.campaign_id,
      campaign_name: keyword.campaign_name,
      impressions: keyword.impressions,
      clicks: keyword.clicks,
      cost: keyword.cost,
      conversions: keyword.conversions,
      ctr: keyword.clicks > 0 ? parseFloat((keyword.clicks / keyword.impressions * 100).toFixed(2)) : 0,
      cpc: keyword.clicks > 0 ? parseFloat((keyword.cost / keyword.clicks).toFixed(2)) : 0
    }));

    // Campaign comparison chart: renderCampaignComparison reads {name, cost,
    // conversions}. Derived from the same campaigns array (no extra query).
    const campaign_comparison = campaigns.map(c => ({
      name: c.name,
      cost: c.cost,
      conversions: c.conversions
    }));

    return new Response(JSON.stringify({
      account,
      campaigns,
      trend,
      top_keywords,
      campaign_comparison
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Metrics error:', error);
    return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}
