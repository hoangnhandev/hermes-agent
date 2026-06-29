export async function handleMetrics(request, env) {
  try {
    const url = new URL(request.url);
    const dateFrom = url.searchParams.get('date_from');
    const dateTo = url.searchParams.get('date_to');
    const campaignId = url.searchParams.get('campaign_id');

    // Build base query for per-campaign metrics
    let query = `
      SELECT
        c.campaign_id,
        c.name as campaign_name,
        c.has_conversion_tracking,
        COALESCE(SUM(dm.impressions), 0) as impressions,
        COALESCE(SUM(dm.clicks), 0) as clicks,
        COALESCE(SUM(dm.cost), 0) as cost,
        COALESCE(SUM(dm.conversions), 0) as conversions,
        COALESCE(SUM(dm.conversion_value), 0) as conversion_value
      FROM campaigns c
      LEFT JOIN daily_metrics dm ON c.campaign_id = dm.entity_id
        AND dm.entity_type = 'campaign'
    `;

    const queryParams = [];

    // Add date filters if provided
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

    // Add campaign filter if provided
    if (campaignId) {
      query += ' AND c.campaign_id = ?';
      queryParams.push(campaignId);
    }

    query += ' GROUP BY c.campaign_id, c.name, c.has_conversion_tracking';

    const campaignsResult = await env.DB.prepare(query).bind(...queryParams).all();

    // Calculate KPIs for each campaign
    const campaigns = campaignsResult.results.map(campaign => {
      const ctr = campaign.clicks > 0 ? (campaign.clicks / campaign.impressions) * 100 : 0;
      const cpc = campaign.clicks > 0 ? campaign.cost / campaign.clicks : 0;
      const cpl = campaign.conversions > 0 ? campaign.cost / campaign.conversions : null;

      return {
        campaign_id: campaign.campaign_id,
        campaign_name: campaign.campaign_name,
        has_conversion_tracking: !!campaign.has_conversion_tracking,
        impressions: campaign.impressions,
        clicks: campaign.clicks,
        cost: campaign.cost,
        conversions: campaign.conversions,
        conversion_value: campaign.conversion_value,
        ctr: parseFloat(ctr.toFixed(2)),
        cpc: parseFloat(cpc.toFixed(2)),
        cpl: cpl ? parseFloat(cpl.toFixed(2)) : null
      };
    });

    // Calculate account totals in JavaScript (not SQL)
    const accountTotals = campaigns.reduce((acc, campaign) => {
      acc.impressions += campaign.impressions;
      acc.clicks += campaign.clicks;
      acc.cost += campaign.cost;
      acc.conversions += campaign.conversions;
      acc.conversion_value += campaign.conversion_value;
      return acc;
    }, {
      impressions: 0,
      clicks: 0,
      cost: 0,
      conversions: 0,
      conversion_value: 0
    });

    const accountKPIs = {
      impressions: accountTotals.impressions,
      clicks: accountTotals.clicks,
      cost: accountTotals.cost,
      conversions: accountTotals.conversions,
      conversion_value: accountTotals.conversion_value,
      ctr: accountTotals.clicks > 0 ? parseFloat((accountTotals.clicks / accountTotals.impressions * 100).toFixed(2)) : 0,
      cpc: accountTotals.clicks > 0 ? parseFloat((accountTotals.cost / accountTotals.clicks).toFixed(2)) : 0,
      cpl: accountTotals.conversions > 0 ? parseFloat((accountTotals.cost / accountTotals.conversions).toFixed(2)) : null
    };

    // Get trend data (last 30 days)
    const trendQuery = `
      SELECT
        date,
        SUM(impressions) as impressions,
        SUM(clicks) as clicks,
        SUM(cost) as cost,
        SUM(conversions) as conversions
      FROM daily_metrics
      WHERE entity_type = 'campaign'
        AND date >= date('now', '-30 days')
      GROUP BY date
      ORDER BY date
    `;

    const trendResult = await env.DB.prepare(trendQuery).all();
    const trend = trendResult.results.map(row => ({
      date: row.date,
      impressions: row.impressions,
      clicks: row.clicks,
      cost: row.cost,
      conversions: row.conversions,
      ctr: row.clicks > 0 ? parseFloat((row.clicks / row.impressions * 100).toFixed(2)) : 0,
      cpc: row.clicks > 0 ? parseFloat((row.cost / row.clicks).toFixed(2)) : 0
    }));

    // Get top keywords
    const topKeywordsQuery = `
      SELECT
        k.text,
        k.campaign_id,
        c.name as campaign_name,
        COALESCE(SUM(dm.impressions), 0) as impressions,
        COALESCE(SUM(dm.clicks), 0) as clicks,
        COALESCE(SUM(dm.cost), 0) as cost
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
      ctr: keyword.clicks > 0 ? parseFloat((keyword.clicks / keyword.impressions * 100).toFixed(2)) : 0,
      cpc: keyword.clicks > 0 ? parseFloat((keyword.cost / keyword.clicks).toFixed(2)) : 0
    }));

    return new Response(JSON.stringify({
      campaigns,
      kpis: accountKPIs,
      trend,
      top_keywords
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