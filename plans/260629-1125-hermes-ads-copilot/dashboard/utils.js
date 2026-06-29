function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function formatCurrency(amount) {
    return '$' + amount.toFixed(2);
}

function formatPercent(value) {
    return (value * 100).toFixed(2) + '%';
}

async function fetchWithAuth(path) {
    try {
        let response = await fetch(path, {
            credentials: 'include'
        });

        if (response.status === 401) {
            const refreshSuccess = await refreshAndRedirect();
            if (!refreshSuccess) {
                throw new Error('Authentication failed');
            }

            response = await fetch(path, {
                credentials: 'include'
            });
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('Fetch error:', error);
        throw error;
    }
}

async function loadTabContent(tabId) {
    try {
        const response = await fetch(`tab-${tabId}.html`);
        if (response.ok) {
            const content = await response.text();
            const container = document.getElementById(`${tabId}-content`);
            if (container) {
                container.innerHTML = content;
            }
        }
    } catch (error) {
        console.error(`Failed to load ${tabId} tab content:`, error);
    }
}

function showEmptyState(tabId) {
    const tabContent = document.getElementById(tabId + '-tab');
    if (!tabContent) return;

    const charts = tabContent.querySelectorAll('canvas');
    charts.forEach(canvas => {
        const existingChart = Chart.getChart(canvas);
        if (existingChart) {
            existingChart.destroy();
        }
    });

    const tables = tabContent.querySelectorAll('tbody');
    tables.forEach(tbody => {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-state">No data available yet</td></tr>';
    });
}

function updateLastUpdated() {
    const now = new Date();
    document.getElementById('lastUpdated').textContent =
        `Last updated: ${now.toLocaleDateString()} ${now.toLocaleTimeString()}`;
}