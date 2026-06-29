if (!checkAuth()) {
    window.location.href = 'index.html';
}

function renderCopyKeywords(data) {
    if (!data) {
        showEmptyState('keywords');
        return;
    }

    const bestAdCopy = document.getElementById('bestAdCopy');
    if (data.best_ad_copy && bestAdCopy) {
        bestAdCopy.innerHTML = data.best_ad_copy.map(copy => `
            <div style="background: var(--bg-tertiary); padding: 1rem; border-radius: var(--radius); margin-bottom: 1rem;">
                <h4 style="margin-bottom: 0.5rem;">${copy.headline}</h4>
                <p style="color: var(--text-secondary); font-size: 0.875rem;">${copy.description}</p>
                <div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--accent-green);">
                    CTR: ${formatPercent(copy.ctr)} | Conversions: ${copy.conversions}
                </div>
            </div>
        `).join('');
    }

    if (data.keywords) {
        const tbody = document.getElementById('keywordPerformanceTableBody');
        if (tbody) {
            tbody.innerHTML = data.keywords.slice(0, 10).map(keyword => `
                <tr>
                    <td>${keyword.text}</td>
                    <td>${formatNumber(keyword.impressions)}</td>
                    <td>${formatNumber(keyword.clicks)}</td>
                    <td>${formatPercent(keyword.ctr)}</td>
                    <td>${formatCurrency(keyword.cpc)}</td>
                    <td>${keyword.conversions || 0}</td>
                </tr>
            `).join('');
        }
    }

    const suggestions = document.getElementById('optimizationSuggestions');
    if (data.suggestions && suggestions) {
        suggestions.innerHTML = data.suggestions.map(suggestion => `
            <div style="background: var(--bg-tertiary); padding: 1rem; border-radius: var(--radius); margin-bottom: 1rem;">
                <h4 style="margin-bottom: 0.5rem;">${suggestion.type}</h4>
                <p style="color: var(--text-secondary); font-size: 0.875rem;">${suggestion.description}</p>
                <div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--accent-blue);">
                    Impact: ${suggestion.impact}
                </div>
            </div>
        `).join('');
    }
}

function renderBudget(data) {
    if (!data) {
        showEmptyState('budget');
        return;
    }

    const budgetProgress = document.getElementById('budgetProgress');
    const budgetPercent = document.getElementById('budgetPercent');
    const totalBudget = document.getElementById('totalBudget');

    if (data.monthly_budget && budgetProgress && budgetPercent && totalBudget) {
        const percentUsed = (data.spent / data.monthly_budget) * 100;
        budgetProgress.style.width = Math.min(percentUsed, 100) + '%';
        budgetPercent.textContent = percentUsed.toFixed(1) + '%';
        totalBudget.textContent = formatCurrency(data.monthly_budget);

        if (percentUsed < 60) {
            budgetProgress.className = 'progress-fill';
        } else if (percentUsed <= 90) {
            budgetProgress.className = 'progress-fill yellow';
        } else {
            budgetProgress.className = 'progress-fill red';
        }
    }

    document.getElementById('budget-daily-avg').textContent = formatCurrency(data.daily_average || 0);
    document.getElementById('budget-today').textContent = formatCurrency(data.today_spend || 0);
    document.getElementById('budget-pacing').textContent = formatPercent(data.pacing || 0);
    document.getElementById('budget-forecast').textContent = formatCurrency(data.eom_forecast || 0);

    if (data.spend_trend) {
        renderSpendTrend(data.spend_trend);
    }

    if (data.pacing) {
        renderPerCampaignPacingTable(data.pacing);
    }
}

async function loadAll() {
    try {
        const [metrics, leads, budget, keywords] = await Promise.all([
            fetchWithAuth('/api/metrics'),
            fetchWithAuth('/api/leads'),
            fetchWithAuth('/api/budget'),
            fetchWithAuth('/api/keywords')
        ]);

        renderOverview(metrics);
        renderLeads(leads);
        renderBudget(budget);
        renderCopyKeywords(keywords);

        updateLastUpdated();
    } catch (error) {
        console.error('Error loading data:', error);
    }
}

function setupTabSwitching() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.dataset.tab;

            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            const targetContent = document.getElementById(targetTab + '-tab');
            if (targetContent) {
                targetContent.classList.add('active');
                loadTabContent(targetTab);
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    setupTabSwitching();
    loadTabContent('overview');
    loadAll();

    setInterval(loadAll, 15 * 60 * 1000);
});