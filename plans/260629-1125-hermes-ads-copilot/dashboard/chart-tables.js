function renderPerCampaignTable(campaigns) {
    const tbody = document.getElementById('campaignTableBody');
    if (!tbody) return;

    if (!campaigns || campaigns.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-state">No campaign data available</td></tr>';
        return;
    }

    tbody.innerHTML = campaigns.map(campaign => {
        const cpl = campaign.conversions > 0 ? campaign.cost / campaign.conversions : 'N/A';
        const pacingClass = campaign.pacing > 110 ? 'pacing-red' :
                           campaign.pacing < 90 ? 'pacing-yellow' : 'pacing-green';

        return `
            <tr>
                <td>${campaign.name}</td>
                <td>${campaign.status}</td>
                <td>${campaign.objective}</td>
                <td>${formatNumber(campaign.impressions)}</td>
                <td>${formatNumber(campaign.clicks)}</td>
                <td>${((campaign.clicks / campaign.impressions) * 100).toFixed(2)}%</td>
                <td>$${campaign.cpc.toFixed(2)}</td>
                <td>${campaign.conversions || 'N/A'}</td>
                <td>${cpl === 'N/A' ? 'N/A' : '$' + cpl.toFixed(2)}</td>
                <td class="${pacingClass}">${campaign.pacing.toFixed(1)}%</td>
            </tr>
        `;
    }).join('');
}

function renderTopKeywordsTable(keywords) {
    const tbody = document.getElementById('topKeywordsTableBody');
    if (!tbody) return;

    if (!keywords || keywords.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No keyword data available</td></tr>';
        return;
    }

    tbody.innerHTML = keywords.slice(0, 10).map(keyword => `
        <tr>
            <td>${keyword.text}</td>
            <td>${formatNumber(keyword.impressions)}</td>
            <td>${formatNumber(keyword.clicks)}</td>
            <td>${((keyword.clicks / keyword.impressions) * 100).toFixed(2)}%</td>
            <td>$${keyword.cpc.toFixed(2)}</td>
            <td>${keyword.conversions || 0}</td>
        </tr>
    `).join('');
}

function renderSpendTrend(trend) {
    destroyChartIfExists('spendTrendChart');

    if (!trend || trend.length === 0) return;

    const ctx = document.getElementById('spendTrendChart').getContext('2d');
    const avgSpend = trend.reduce((sum, item) => sum + item.spend, 0) / trend.length;

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: trend.map(item => item.date),
            datasets: [
                {
                    label: 'Daily Spend',
                    data: trend.map(item => item.spend),
                    backgroundColor: CHART_COLORS.blue
                },
                {
                    label: 'Daily Average',
                    data: trend.map(() => avgSpend),
                    type: 'line',
                    borderColor: CHART_COLORS.orange,
                    backgroundColor: CHART_COLORS.orange,
                    borderWidth: 2,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Spend ($)' }
                },
                x: {
                    title: { display: true, text: 'Date' }
                }
            }
        }
    });
}

function renderPerCampaignPacingTable(pacing) {
    const tbody = document.getElementById('pacingTableBody');
    if (!tbody) return;

    if (!pacing || pacing.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No pacing data available</td></tr>';
        return;
    }

    tbody.innerHTML = pacing.map(campaign => {
        const pacingClass = campaign.pacing_percent > 110 ? 'pacing-red' :
                           campaign.pacing_percent < 90 ? 'pacing-yellow' : 'pacing-green';

        return `
            <tr>
                <td>${campaign.name}</td>
                <td>$${campaign.daily_budget.toFixed(2)}</td>
                <td>$${campaign.spent.toFixed(2)}</td>
                <td class="${pacingClass}">${campaign.pacing_percent.toFixed(1)}%</td>
                <td>${campaign.status}</td>
            </tr>
        `;
    }).join('');
}