export async function handleLeads(request, env) {
  try {
    const url = new URL(request.url);
    const dateFrom = url.searchParams.get('date_from');
    const dateTo = url.searchParams.get('date_to');
    const campaignId = url.searchParams.get('campaign_id');

    // Build query for leads (only from campaigns with conversion tracking)
    let query = `
      SELECT
        l.id,
        l.campaign_id,
        c.name as campaign_name,
        l.conversion_id,
        l.source,
        l.conversion_date,
        l.conversion_value,
        l.created_at
      FROM leads l
      INNER JOIN campaigns c ON l.campaign_id = c.campaign_id
      WHERE c.has_conversion_tracking = 1
    `;

    const queryParams = [];

    // Add date filters if provided
    if (dateFrom || dateTo) {
      query += ' AND';
      if (dateFrom && dateTo) {
        query += ' l.conversion_date BETWEEN ? AND ?';
        queryParams.push(dateFrom, dateTo);
      } else if (dateFrom) {
        query += ' l.conversion_date >= ?';
        queryParams.push(dateFrom);
      } else {
        query += ' l.conversion_date <= ?';
        queryParams.push(dateTo);
      }
    }

    // Add campaign filter if provided
    if (campaignId) {
      query += ' AND l.campaign_id = ?';
      queryParams.push(campaignId);
    }

    query += ' ORDER BY l.conversion_date DESC';

    const leadsResult = await env.DB.prepare(query).bind(...queryParams).all();
    const leads = leadsResult.results;

    // Calculate summary statistics
    const totalLeads = leads.length;
    const totalValue = leads.reduce((sum, lead) => sum + (lead.conversion_value || 0), 0);
    const avgValue = totalLeads > 0 ? totalValue / totalLeads : 0;

    // Group by campaign for breakdown
    const campaignBreakdown = {};
    leads.forEach(lead => {
      if (!campaignBreakdown[lead.campaign_id]) {
        campaignBreakdown[lead.campaign_id] = {
          campaign_id: lead.campaign_id,
          campaign_name: lead.campaign_name,
          leads: 0,
          total_value: 0
        };
      }
      campaignBreakdown[lead.campaign_id].leads++;
      campaignBreakdown[lead.campaign_id].total_value += lead.conversion_value || 0;
    });

    const summary = {
      total_leads: totalLeads,
      total_value: parseFloat(totalValue.toFixed(2)),
      avg_value_per_lead: parseFloat(avgValue.toFixed(2)),
      campaign_breakdown: Object.values(campaignBreakdown).map(campaign => ({
        ...campaign,
        avg_value_per_lead: campaign.leads > 0 ? parseFloat((campaign.total_value / campaign.leads).toFixed(2)) : 0
      }))
    };

    // Get trend data (daily lead counts for last 30 days)
    let trendQuery = `
      SELECT
        DATE(conversion_date) as date,
        COUNT(*) as leads,
        SUM(conversion_value) as total_value
      FROM leads l
      INNER JOIN campaigns c ON l.campaign_id = c.campaign_id
      WHERE c.has_conversion_tracking = 1
        AND conversion_date >= date('now', '-30 days')
    `;

    const trendParams = [];
    if (campaignId) {
      trendQuery += ' AND l.campaign_id = ?';
      trendParams.push(campaignId);
    }

    trendQuery += ' GROUP BY DATE(conversion_date) ORDER BY date';

    const trendResult = await env.DB.prepare(trendQuery).bind(...trendParams).all();
    const trend = trendResult.results.map(row => ({
      date: row.date,
      leads: row.leads,
      total_value: parseFloat((row.total_value || 0).toFixed(2)),
      avg_value: row.leads > 0 ? parseFloat((row.total_value / row.leads).toFixed(2)) : 0
    }));

    // Get source breakdown
    let sourceQuery = `
      SELECT
        source,
        COUNT(*) as leads,
        SUM(conversion_value) as total_value
      FROM leads l
      INNER JOIN campaigns c ON l.campaign_id = c.campaign_id
      WHERE c.has_conversion_tracking = 1
    `;

    const sourceParams = [];
    if (dateFrom || dateTo) {
      sourceQuery += ' AND';
      if (dateFrom && dateTo) {
        sourceQuery += ' l.conversion_date BETWEEN ? AND ?';
        sourceParams.push(dateFrom, dateTo);
      } else if (dateFrom) {
        sourceQuery += ' l.conversion_date >= ?';
        sourceParams.push(dateFrom);
      } else {
        sourceQuery += ' l.conversion_date <= ?';
        sourceParams.push(dateTo);
      }
    }

    if (campaignId) {
      sourceQuery += ' AND l.campaign_id = ?';
      sourceParams.push(campaignId);
    }

    sourceQuery += ' GROUP BY source';

    const sourceResult = await env.DB.prepare(sourceQuery).bind(...sourceParams).all();
    const source_breakdown = sourceResult.results.map(source => ({
      source: source.source,
      leads: source.leads,
      total_value: parseFloat((source.total_value || 0).toFixed(2)),
      avg_value: source.leads > 0 ? parseFloat((source.total_value / source.leads).toFixed(2)) : 0
    }));

    return new Response(JSON.stringify({
      leads,
      summary,
      trend,
      source_breakdown
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Leads error:', error);
    return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}