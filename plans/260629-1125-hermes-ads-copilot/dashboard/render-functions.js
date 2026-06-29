function renderOverview(data) {
    if (!data) {
        showEmptyState('overview');
        return;
    }

    const account = data.account || {};
    document.getElementById('overview-impressions').textContent = formatNumber(account.impressions || 0);
    document.getElementById('overview-clicks').textContent = formatNumber(account.clicks || 0);
    document.getElementById('overview-ctr').textContent = formatPercent(account.ctr || 0);

    const avgCpc = account.clicks > 0 ? (account.cost / account.clicks) : 0;
    document.getElementById('overview-cpc').textContent = formatCurrency(avgCpc);

    document.getElementById('overview-conversions').textContent = account.conversions || 'N/A';

    const cpl = account.conversions > 0 ? (account.cost / account.conversions) : null;
    document.getElementById('overview-cpl').textContent = cpl ? formatCurrency(cpl) : 'N/A';

    document.getElementById('overview-spend').textContent = formatCurrency(account.cost || 0);

    const convRate = account.clicks > 0 ? (account.conversions / account.clicks) : 0;
    document.getElementById('overview-conv-rate').textContent = formatPercent(convRate);

    if (data.campaigns) {
        renderPerCampaignTable(data.campaigns);
    }

    if (data.trend) {
        renderPerformanceTrend(data.trend);
    }

    if (data.campaign_comparison) {
        renderCampaignComparison(data.campaign_comparison);
    }

    if (data.top_keywords) {
        renderTopKeywordsTable(data.top_keywords);
    }
}

function renderLeads(data) {
    if (!data) {
        showEmptyState('leads');
        return;
    }

    document.getElementById('leads-today').textContent = formatNumber(data.today || 0);
    document.getElementById('leads-week').textContent = formatNumber(data.week || 0);
    document.getElementById('leads-alltime').textContent = formatNumber(data.all_time || 0);
    document.getElementById('leads-quality').textContent = (data.avg_quality || 0).toFixed(2);

    if (data.trend) {
        renderLeadTrend(data.trend);
    }

    if (data.sources) {
        renderLeadSources(data.sources);
    }
}

function renderLeadTrend(trend) {
    destroyChartIfExists('leadTrendChart');

    if (!trend || trend.length === 0) return;

    const ctx = document.getElementById('leadTrendChart').getContext('2d');

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: trend.map(item => item.date),
            datasets: [{
                label: 'Leads',
                data: trend.map(item => item.leads),
                borderColor: CHART_COLORS.blue,
                backgroundColor: CHART_COLORS.blue + '20',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Number of Leads' }
                },
                x: {
                    title: { display: true, text: 'Date' }
                }
            }
        }
    });
}

function renderLeadSources(sources) {
    destroyChartIfExists('leadSourcesChart');

    if (!sources || sources.length === 0) return;

    const ctx = document.getElementById('leadSourcesChart').getContext('2d');

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: sources.map(s => s.source),
            datasets: [{
                data: sources.map(s => s.leads),
                backgroundColor: Object.values(CHART_COLORS)
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });
}