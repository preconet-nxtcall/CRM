/* js/pipeline.js - Neodove Logic */

class PipelineManager {
    constructor() {
        this.currentStatusFilter = 'all';
        this.currentPage = 1;
        this.pipelineData = {};

        // Month selector for agent performance
        const now = new Date();
        this.currentMonth = now.getMonth() + 1; // 1-12
        this.currentYear = now.getFullYear();
    }

    async init() {
        await Promise.all([
            this.loadStats(),
            this.loadLeads(),
            this.loadAgents()
        ]);
    }

    /* ------------------------------------------------
       1. Stats & Pipeline Bar
    ------------------------------------------------ */
    async loadStats() {
        try {
            const offset = new Date().getTimezoneOffset();
            const resp = await auth.makeAuthenticatedRequest(`/api/pipeline/stats?timezone_offset=${offset}`);
            if (resp && resp.ok) {
                const data = await resp.json();
                this.renderKPIs(data.kpis);
                this.renderPipelineBar(data.pipeline);
                this.renderChart(data.pipeline);
                this.renderFunnel(data.pipeline);
            }
        } catch (e) {
            console.error("Stats Error:", e);
        }
    }

    renderKPIs(kpis) {
        document.getElementById('kpi-total-leads').textContent = kpis.total_leads || 0;
        document.getElementById('kpi-new-today').textContent = kpis.new_leads_today || 0;
        document.getElementById('kpi-calls-today').textContent = kpis.calls_made_today || 0;
        document.getElementById('kpi-connected').textContent = kpis.connected_calls_today || 0;
        document.getElementById('kpi-conversion').textContent = (kpis.conversion_rate || 0) + '%';
    }

    renderPipelineBar(pipeline) {
        const container = document.getElementById('pipeline-container');
        if (!container) return;

        // Force Fixed Order - Match Leads Page Statuses
        const stages = [
            { key: 'New', color: 'blue' },
            { key: 'Attempted', color: 'yellow' },
            { key: 'Interested', color: 'purple' },
            { key: 'Follow-Up', color: 'pink' },
            { key: 'Converted', color: 'indigo' },
            { key: 'Won', color: 'green' },
            { key: 'Lost', color: 'red' }
        ];

        container.innerHTML = stages.map(stage => {
            const count = pipeline[stage.key] || 0;
            const isActive = this.currentStatusFilter === stage.key;

            return `
                <div class="flex-1 min-w-[100px] p-4 text-center border-r border-gray-100 hover:bg-gray-50 cursor-pointer pipeline-segment ${isActive ? 'bg-blue-50 border-b-2 border-blue-500' : ''}"
                     onclick="pipelineManager.filterByStatus('${stage.key}')">
                    <p class="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1">${stage.key}</p>
                    <p class="text-2xl font-bold text-${stage.color}-600 leading-none">${count}</p>
                </div>
            `;
        }).join('');
    }

    filterByStatus(status) {
        if (this.currentStatusFilter === status) {
            this.currentStatusFilter = 'all'; // Toggle off
        } else {
            this.currentStatusFilter = status;
        }

        // Update UI Look (Simple Refresh)
        this.loadStats(); // To refresh highlights
        this.loadLeads(1); // Reset page

        const label = document.getElementById('current-filter-label');
        if (label) label.textContent = this.currentStatusFilter === 'all' ? 'All Leads' : `Status: ${status}`;
    }

    /* ------------------------------------------------
       2. Leads Table
    ------------------------------------------------ */
    // Updated for SPA: IDs must be unique
    async loadLeads(page = 1) {
        try {
            this.currentPage = page;
            const tbody = document.getElementById('pipeline-leads-table-body'); // Updated ID
            if (!tbody) return;

            tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-8 text-center text-gray-400"><i class="fas fa-spinner fa-spin mr-2"></i>Loading...</td></tr>';

            let url = `/api/facebook/leads?page=${page}&per_page=10&date_filter=today`;
            if (this.currentStatusFilter !== 'all') {
                url += `&status=${encodeURIComponent(this.currentStatusFilter)}`;
            }

            const resp = await auth.makeAuthenticatedRequest(url);
            if (resp && resp.ok) {
                const data = await resp.json();
                this.renderLeadsTable(data.leads);
                this.updatePagination(data.pagination);
            }
        } catch (e) {
            console.error("Leads Error:", e);
        }
    }

    renderLeadsTable(leads) {
        const tbody = document.getElementById('pipeline-leads-table-body'); // Updated ID
        if (!tbody) return;

        if (!leads || leads.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-8 text-center text-gray-400">No leads found.</td></tr>';
            return;
        }

        tbody.innerHTML = leads.map(lead => {
            // Status Badge Logic
            // Status Badge Logic
            let badgeClass = 'bg-gray-100 text-gray-600';
            const s = (lead.status || '').toLowerCase();

            if (s === 'new') badgeClass = 'bg-blue-50 text-blue-700 border border-blue-100';

            else if (['attempted', 'ringing', 'busy', 'not reachable', 'switch off', 'no answer', 'connected', 'contacted', 'in conversation'].includes(s))
                badgeClass = 'bg-yellow-50 text-yellow-800 border border-yellow-100';

            else if (['interested', 'meeting scheduled', 'demo scheduled'].includes(s))
                badgeClass = 'bg-purple-50 text-purple-700 border border-purple-100';

            else if (['follow-up', 'follow up', 'call later', 'callback'].includes(s))
                badgeClass = 'bg-pink-50 text-pink-700 border border-pink-100';

            else if (s === 'converted')
                badgeClass = 'bg-indigo-50 text-indigo-700 border border-indigo-100';

            else if (['won', 'closed'].includes(s))
                badgeClass = 'bg-green-50 text-green-700 border border-green-100';

            else if (['lost', 'junk', 'wrong number', 'invalid', 'not interested', 'not intersted'].includes(s))
                badgeClass = 'bg-red-50 text-red-700 border border-red-100';

            // Date Format (Local Time)
            const dateStr = lead.last_activity ? new Date(lead.last_activity).toLocaleString('en-IN', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true
            }) : '-';

            return `
                <tr class="hover:bg-gray-50 transition-colors group">
                    <td class="px-6 py-3 font-medium text-gray-900">
                        <div class="flex flex-col">
                            <span>${lead.name}</span>
                            <span class="text-xs text-blue-600 font-normal group-hover:underline cursor-pointer">${lead.phone}</span>
                        </div>
                    </td>
                    <td class="px-6 py-3">
                         <span class="px-2 py-0.5 text-[10px] font-bold uppercase bg-gray-100 text-gray-500 rounded">${lead.source}</span>
                    </td>
                    <td class="px-6 py-3 text-gray-600">${lead.agent}</td>
                    <td class="px-6 py-3">
                        <span class="px-2.5 py-0.5 text-xs font-medium rounded-full ${badgeClass}">${lead.status}</span>
                    </td>
                    <td class="px-6 py-3 text-xs text-gray-500">${dateStr}</td>
                </tr>
            `;
        }).join('');
    }

    updatePagination(pageData) {
        const prevBtn = document.getElementById('pl-prev-page-btn'); // Updated ID
        const nextBtn = document.getElementById('pl-next-page-btn'); // Updated ID
        const label = document.getElementById('pl-page-info'); // Updated ID

        if (prevBtn) {
            prevBtn.disabled = pageData.current <= 1;
            prevBtn.onclick = () => this.loadLeads(pageData.current - 1);
        }
        if (nextBtn) {
            nextBtn.disabled = pageData.current >= pageData.pages;
            nextBtn.onclick = () => this.loadLeads(pageData.current + 1);
        }
        if (label) {
            label.textContent = `Page ${pageData.current} of ${pageData.pages}`;
        }
    }

    /* ------------------------------------------------
       3. Agents Table
    ------------------------------------------------ */
    async loadAgents(month = null, year = null) {
        try {
            // Use provided month/year or current values
            const targetMonth = month || this.currentMonth;
            const targetYear = year || this.currentYear;

            const url = `/api/pipeline/agents?month=${targetMonth}&year=${targetYear}`;
            const resp = await auth.makeAuthenticatedRequest(url);
            if (resp && resp.ok) {
                const data = await resp.json();
                const tbody = document.getElementById('pipeline-agent-table-body'); // Updated ID
                if (!tbody) return;

                tbody.innerHTML = (data.agents || []).slice(0, 5).map(a => `
                    <tr class="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                        <td class="px-4 py-2 font-medium text-gray-800">${a.name}</td>
                        <td class="px-4 py-2 text-right text-gray-600">${a.calls_made}</td>
                        <td class="px-4 py-2 text-right font-medium text-green-600">${a.closed_leads}</td>
                    </tr>
                `).join('');

                // Update month selector display if exists
                this.updateMonthDisplay(data.month, data.year);
            }
        } catch (e) {
            console.error("Agents Error:", e);
        }
    }

    changeAgentMonth(direction) {
        // direction: 1 for next month, -1 for previous month
        this.currentMonth += direction;

        if (this.currentMonth > 12) {
            this.currentMonth = 1;
            this.currentYear++;
        } else if (this.currentMonth < 1) {
            this.currentMonth = 12;
            this.currentYear--;
        }

        this.loadAgents(this.currentMonth, this.currentYear);
    }

    updateMonthDisplay(month, year) {
        const display = document.getElementById('agent-month-display');
        if (display) {
            const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            display.textContent = `${monthNames[month - 1]} ${year}`;
        }
    }

    /* ------------------------------------------------
       4. Chart
    ------------------------------------------------ */
    renderChart(pipeline) {
        const ctx = document.getElementById('pipelineChart');
        if (!ctx) return;

        // Note: Chart.js might fail if canvas is reused or not destroyed. 
        // For simple switching, we might want to check if a chart instance exists on the canvas and destroy it.
        const existingChart = Chart.getChart(ctx);
        if (existingChart) existingChart.destroy();

        const dataValues = [
            pipeline['New'] || 0,
            pipeline['Attempted'] || 0,
            pipeline['Interested'] || 0,
            pipeline['Follow-Up'] || 0,
            pipeline['Converted'] || 0,
            pipeline['Won'] || 0,
            pipeline['Lost'] || 0
        ];

        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['New', 'Attempted', 'Interested', 'Follow-Up', 'Converted', 'Won', 'Lost'],
                datasets: [{
                    data: dataValues,
                    backgroundColor: ['#3b82f6', '#fbbf24', '#a855f7', '#ec4899', '#6366f1', '#22c55e', '#ef4444'],
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
                plugins: {
                    legend: { position: 'right', labels: { boxWidth: 10, font: { size: 10 } } }
                }
            }
        });
    }
    /* ------------------------------------------------
       2.5 Funnel Graph
    ------------------------------------------------ */
    renderFunnel(pipe) {
        const container = document.getElementById('pipeline-funnel-container');
        const metrics = document.getElementById('pipeline-funnel-metrics');
        if (!container) return;

        if (!pipe) {
            container.innerHTML = '<div class="text-center text-red-400">No data available.</div>';
            return;
        }

        try {
            // Map API keys to our Funnel Stages
            const stages = [
                { id: 'new', label: 'New Leads', icon: 'fa-star', count: pipe['New'] || 0, color: 'funnel-new' },
                { id: 'attempted', label: 'Attempted', icon: 'fa-phone', count: pipe['Attempted'] || 0, color: 'funnel-attempted' },
                { id: 'connected', label: 'Connected', icon: 'fa-comments', count: (pipe['Connected'] || 0) + (pipe['Follow-Up'] || 0), color: 'funnel-connected' },
                { id: 'interested', label: 'Interested', icon: 'fa-thumbs-up', count: pipe['Interested'] || 0, color: 'funnel-interested' },
                { id: 'won', label: 'Won / Closed', icon: 'fa-trophy', count: pipe['Won'] || 0, color: 'funnel-won' }
            ];

            // Render Funnel
            container.innerHTML = stages.map(stage => `
                 <div class="funnel-row">
                     <div class="funnel-segment ${stage.color}">
                         <div class="funnel-label">
                             <i class="fas ${stage.icon}"></i> ${stage.label}
                         </div>
                         <div class="funnel-count">${stage.count}</div>
                     </div>
                 </div>
             `).join('');

            // Calculate Conversion Metrics
            const total = stages[0].count;
            const won = stages[4].count;
            const conversionRate = total > 0 ? ((won / total) * 100).toFixed(1) : 0;

            metrics.innerHTML = `
                 <div class="px-3 py-1 bg-green-50 text-green-700 rounded-full border border-green-100 flex items-center gap-2">
                     <i class="fas fa-chart-line"></i> Overall Conversion: <strong>${conversionRate}%</strong>
                 </div>
                 <div class="px-3 py-1 bg-blue-50 text-blue-700 rounded-full border border-blue-100 flex items-center gap-2">
                     <i class="fas fa-users"></i> Total Leads: <strong>${total}</strong>
                 </div>
             `;
        } catch (e) {
            console.error("Funnel Render Error:", e);
            container.innerHTML = '<div class="text-center text-red-400">Error rendering funnel.</div>';
        }
    }
}

window.pipelineManager = new PipelineManager();
// Remove auto-init
// window.pipelineManager.init();
