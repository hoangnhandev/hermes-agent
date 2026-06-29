Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
Chart.defaults.color = '#e6edf3';
Chart.defaults.borderColor = '#30363d';

Chart.defaults.scale.grid.color = '#30363d';
Chart.defaults.scale.ticks.color = '#8b949e';
Chart.defaults.scale.title.color = '#e6edf3';

const CHART_COLORS = {
    blue: '#58a6ff',
    green: '#3fb950',
    red: '#f85149',
    yellow: '#d29922',
    purple: '#bc8cff',
    orange: '#fd7e14',
    cyan: '#17a2b8'
};

function destroyChartIfExists(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (canvas) {
        const existingChart = Chart.getChart(canvas);
        if (existingChart) {
            existingChart.destroy();
        }
    }
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function renderPerformanceTrend(trend) {
    destroyChartIfExists('performanceTrendChart');

    if (!trend || trend.length === 0) return;

    const ctx = document.getElementById('performanceTrendChart').getContext('2d');

    const datasets = [];
    const campaigns = [...new Set(trend.map(item => item.campaign))];

    campaigns.forEach((campaign, index) => {
        const campaignData = trend.filter(item => item.campaign === campaign);
        const color = Object.values(CHART_COLORS)[index % Object.values(CHART_COLORS).length];

        datasets.push({
            label: campaign,
            data: campaignData.map(item => ({
                x: item.date,
                y: item.metric_value
            })),
            borderColor: color,
            backgroundColor: color + '20',
            tension: 0.4,
            fill: false
        });
    });

    new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            scales: {
                x: {
                    type: 'time',
                    time: { unit: 'day' },
                    title: { display: true, text: 'Date' }
                },
                y: {
                    title: { display: true, text: 'Value' }
                }
            },
            plugins: {
                legend: { display: true }
            }
        }
    });
}

function renderCampaignComparison(campaigns) {
    destroyChartIfExists('campaignComparisonChart');

    if (!campaigns || campaigns.length === 0) return;

    const ctx = document.getElementById('campaignComparisonChart').getContext('2d');

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: campaigns.map(c => c.name),
            datasets: [
                {
                    label: 'Cost',
                    data: campaigns.map(c => c.cost),
                    backgroundColor: CHART_COLORS.red
                },
                {
                    label: 'Conversions',
                    data: campaigns.map(c => c.conversions),
                    backgroundColor: CHART_COLORS.green
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Value' }
                }
            }
        }
    });
}