export async function handleKeywords(request, env) {
  try {
    // Get all keywords with campaign info
    const keywordsQuery = `
      SELECT
        k.keyword_id,
        k.text,
        k.match_type,
        k.status,
        k.campaign_id,
        c.name as campaign_name,
        k.ad_group_id,
        ag.name as ad_group_name,
        COALESCE(SUM(dm.impressions), 0) as impressions,
        COALESCE(SUM(dm.clicks), 0) as clicks,
        COALESCE(SUM(dm.cost), 0) as cost,
        COALESCE(SUM(dm.conversions), 0) as conversions
      FROM keywords k
      LEFT JOIN campaigns c ON k.campaign_id = c.campaign_id
      LEFT JOIN ad_groups ag ON k.ad_group_id = ag.ad_group_id
      LEFT JOIN daily_metrics dm ON k.keyword_id = dm.entity_id
        AND dm.entity_type = 'keyword'
      GROUP BY k.keyword_id, k.text, k.match_type, k.status, k.campaign_id,
               c.name, k.ad_group_id, ag.name
      ORDER BY k.campaign_id, k.ad_group_id, k.text
    `;

    const keywordsResult = await env.DB.prepare(keywordsQuery).all();
    const keywords = keywordsResult.results.map(keyword => ({
      keyword_id: keyword.keyword_id,
      text: keyword.text,
      match_type: keyword.match_type,
      status: keyword.status,
      campaign_id: keyword.campaign_id,
      campaign_name: keyword.campaign_name,
      ad_group_id: keyword.ad_group_id,
      ad_group_name: keyword.ad_group_name,
      impressions: keyword.impressions,
      clicks: keyword.clicks,
      cost: keyword.cost,
      conversions: keyword.conversions,
      ctr: keyword.clicks > 0 ? parseFloat((keyword.clicks / keyword.impressions * 100).toFixed(2)) : 0,
      cpc: keyword.clicks > 0 ? parseFloat((keyword.cost / keyword.clicks).toFixed(2)) : 0
    }));

    // Get ad copy history for learning/optimization
    const adCopyQuery = `
      SELECT
        ach.id,
        ach.campaign_id,
        c.name as campaign_name,
        ach.headline,
        ach.description,
        ach.approval_status,
        ach.impressions,
        ach.clicks,
        ach.conversions,
        ach.created_at,
        CASE
          WHEN ach.clicks > 0 THEN (ach.conversions * 100.0 / ach.clicks)
          ELSE 0
        END as conversion_rate
      FROM ad_copy_history ach
      LEFT JOIN campaigns c ON ach.campaign_id = c.campaign_id
      ORDER BY ach.created_at DESC
      LIMIT 50
    `;

    const adCopyResult = await env.DB.prepare(adCopyQuery).all();
    const ad_copy = adCopyResult.results.map(copy => ({
      id: copy.id,
      campaign_id: copy.campaign_id,
      campaign_name: copy.campaign_name,
      headline: copy.headline,
      description: copy.description,
      approval_status: copy.approval_status,
      impressions: copy.impressions,
      clicks: copy.clicks,
      conversions: copy.conversions,
      conversion_rate: parseFloat(copy.conversion_rate.toFixed(2)),
      created_at: copy.created_at
    }));

    // Generate keyword suggestions based on performance
    const suggestionsQuery = `
      WITH keyword_performance AS (
        SELECT
          k.text,
          k.match_type,
          k.campaign_id,
          c.name as campaign_name,
          SUM(dm.impressions) as impressions,
          SUM(dm.clicks) as clicks,
          SUM(dm.cost) as cost,
          SUM(dm.conversions) as conversions,
          CASE
            WHEN SUM(dm.clicks) > 0 THEN (SUM(dm.conversions) * 100.0 / SUM(dm.clicks))
            ELSE 0
          END as conversion_rate,
          CASE
            WHEN SUM(dm.clicks) > 0 THEN SUM(dm.cost) / SUM(dm.clicks)
            ELSE 0
          END as cpc
        FROM keywords k
        LEFT JOIN campaigns c ON k.campaign_id = c.campaign_id
        LEFT JOIN daily_metrics dm ON k.keyword_id = dm.entity_id
          AND dm.entity_type = 'keyword'
        GROUP BY k.text, k.match_type, k.campaign_id, c.name
        HAVING SUM(dm.clicks) > 10  -- Only consider keywords with sufficient data
      )
      SELECT
        text,
        campaign_id,
        campaign_name,
        impressions,
        clicks,
        conversions,
        conversion_rate,
        cpc,
        CASE
          WHEN conversion_rate > 5.0 THEN 'High performing - consider increasing bid'
          WHEN conversion_rate > 2.0 AND cpc < 5.0 THEN 'Good performance - maintain current strategy'
          WHEN conversion_rate < 1.0 AND clicks > 50 THEN 'Low conversion rate - consider pausing or improving landing page'
          WHEN cpc > 20.0 AND conversion_rate < 2.0 THEN 'High CPC with low conversion - consider pausing'
          ELSE 'Monitor performance'
        END as suggestion
      FROM keyword_performance
      ORDER BY
        CASE
          WHEN conversion_rate > 5.0 THEN 1
          WHEN conversion_rate > 2.0 AND cpc < 5.0 THEN 2
          WHEN conversion_rate < 1.0 AND clicks > 50 THEN 3
          WHEN cpc > 20.0 AND conversion_rate < 2.0 THEN 4
          ELSE 5
        END,
        clicks DESC
      LIMIT 20
    `;

    const suggestionsResult = await env.DB.prepare(suggestionsQuery).all();
    const suggestions = suggestionsResult.results.map(suggestion => ({
      keyword: suggestion.text,
      campaign_id: suggestion.campaign_id,
      campaign_name: suggestion.campaign_name,
      impressions: suggestion.impressions,
      clicks: suggestion.clicks,
      conversions: suggestion.conversions,
      conversion_rate: parseFloat(suggestion.conversion_rate.toFixed(2)),
      cpc: parseFloat(suggestion.cpc.toFixed(2)),
      suggestion: suggestion.suggestion
    }));

    return new Response(JSON.stringify({
      keywords,
      ad_copy,
      suggestions
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Keywords error:', error);
    return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}