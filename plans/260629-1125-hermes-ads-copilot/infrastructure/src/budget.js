export async function handleBudget(request, env) {
  try {
    const url = new URL(request.url);
    const campaignId = url.searchParams.get('campaign_id');

    // Get current date and month start/end
    const today = new Date();
    const currentMonth = today.toISOString().slice(0, 7); // YYYY-MM format
    const monthStart = `${currentMonth}-01`;
    const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0).toISOString().slice(0, 10);

    // Get per-campaign pacing (primary view)
    let campaignQuery = `
      SELECT
        c.campaign_id,
        c.name as campaign_name,
        c.daily_budget,
        c.monthly_budget,
        COALESCE(SUM(dm.cost), 0) as month_to_date_spend,
        CASE
          WHEN c.daily_budget > 0 THEN (c.monthly_budget / c.daily_budget) * 30.4375
          ELSE c.monthly_budget
        END as estimated_monthly_days,
        CASE
          WHEN c.daily_budget > 0 THEN c.monthly_budget / c.daily_budget
          ELSE 30
        END as budget_days_in_month
      FROM campaigns c
      LEFT JOIN daily_metrics dm ON c.campaign_id = dm.entity_id
        AND dm.entity_type = 'campaign'
        AND dm.date >= ?
        AND dm.date <= ?
      GROUP BY c.campaign_id, c.name, c.daily_budget, c.monthly_budget
      HAVING c.status = 'active'
    `;

    const campaignsResult = await env.DB.prepare(campaignQuery).bind(monthStart, monthEnd).all();
    const per_campaign_pacing = campaignsResult.results.map(campaign => {
      const daysInMonth = campaign.budget_days_in_month || 30;
      const daysElapsed = Math.ceil((today - new Date(monthStart)) / (1000 * 60 * 60 * 24));
      const expectedSpend = (campaign.monthly_budget / daysInMonth) * daysElapsed;
      const pacing = campaign.month_to_date_spend > 0 ?
        (campaign.month_to_date_spend / expectedSpend) * 100 : 0;

      let pacing_status = 'on_track';
      if (pacing < 80) pacing_status = 'under_pacing';
      else if (pacing > 120) pacing_status = 'over_pacing';

      return {
        campaign_id: campaign.campaign_id,
        campaign_name: campaign.campaign_name,
        daily_budget: campaign.daily_budget,
        monthly_budget: campaign.monthly_budget,
        month_to_date_spend: parseFloat(campaign.month_to_date_spend.toFixed(2)),
        remaining_budget: parseFloat((campaign.monthly_budget - campaign.month_to_date_spend).toFixed(2)),
        pacing_pct: parseFloat(pacing.toFixed(1)),
        pacing_status,
        days_remaining: Math.max(0, daysInMonth - daysElapsed),
        recommended_daily_spend: days_remaining > 0 ?
          parseFloat((campaign.monthly_budget - campaign.month_to_date_spend) / days_remaining).toFixed(2) : 0
      };
    });

    // Calculate account totals
    const accountTotals = per_campaign_pacing.reduce((acc, campaign) => {
      acc.total_monthly_budget += campaign.monthly_budget;
      acc.total_month_to_date_spend += campaign.month_to_date_spend;
      return acc;
    }, {
      total_monthly_budget: 0,
      total_month_to_date_spend: 0
    });

    const totalRemainingBudget = accountTotals.total_monthly_budget - accountTotals.total_month_to_date_spend;
    const totalDaysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    const daysElapsed = today.getDate();
    const daysRemaining = totalDaysInMonth - daysElapsed;

    // Get daily spend trend for last 30 days
    const spendTrendQuery = `
      SELECT
        date,
        SUM(cost) as daily_spend
      FROM daily_metrics
      WHERE entity_type = 'campaign'
        AND date >= date('now', '-30 days')
      GROUP BY date
      ORDER BY date
    `;

    const spendTrendResult = await env.DB.prepare(spendTrendQuery).all();
    const spend_trend = spendTrendResult.results.map(row => ({
      date: row.date,
      daily_spend: parseFloat(row.daily_spend.toFixed(2))
    }));

    // Calculate account-level pacing and forecast
    const expectedAccountSpend = (accountTotals.total_monthly_budget / totalDaysInMonth) * daysElapsed;
    const accountPacing = expectedAccountSpend > 0 ?
      (accountTotals.total_month_to_date_spend / expectedAccountSpend) * 100 : 100;

    const averageDailySpend = daysElapsed > 0 ? accountTotals.total_month_to_date_spend / daysElapsed : 0;
    const forecastMonthEndSpend = averageDailySpend * totalDaysInMonth;

    const account_totals = {
      total_monthly_budget: parseFloat(accountTotals.total_monthly_budget.toFixed(2)),
      total_month_to_date_spend: parseFloat(accountTotals.total_month_to_date_spend.toFixed(2)),
      total_remaining_budget: parseFloat(totalRemainingBudget.toFixed(2)),
      daily_avg_spend: parseFloat(averageDailySpend.toFixed(2)),
      today_spend: parseFloat(spend_trend.find(t => t.date === today.toISOString().slice(0, 10))?.daily_spend || 0),
      pacing_pct: parseFloat(accountPacing.toFixed(1)),
      days_elapsed: daysElapsed,
      days_remaining: daysRemaining
    };

    const pacing = {
      status: accountPacing < 80 ? 'under_pacing' : accountPacing > 120 ? 'over_pacing' : 'on_track',
      recommendation: accountPacing < 80 ? 'Increase spend to utilize budget' :
                     accountPacing > 120 ? 'Reduce spend to avoid overspending' :
                     'Maintain current spend level'
    };

    const forecast = {
      projected_month_end_spend: parseFloat(forecastMonthEndSpend.toFixed(2)),
      projected_overspend: Math.max(0, forecastMonthEndSpend - accountTotals.total_monthly_budget),
      projected_underspend: Math.max(0, accountTotals.total_monthly_budget - forecastMonthEndSpend),
      confidence_level: daysElapsed > 20 ? 'high' : daysElapsed > 10 ? 'medium' : 'low'
    };

    return new Response(JSON.stringify({
      per_campaign_pacing,
      account_totals,
      pacing,
      forecast,
      spend_trend
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Budget error:', error);
    return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}