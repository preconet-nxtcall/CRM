/* js/pipeline.js - Neodove Logic */

class PipelineManager {
    constructor() {
        this.currentStatusFilter = 'all';
        this.currentPage = 1;
        this.pipelineData = {};
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

        // Force Fixed Order
        const stages = [
            { key: 'New', color: 'blue' },
            { key: 'Attempted', color: 'yellow' },
            { key: 'Connected', color: 'indigo' },
            { key: 'Interested', color: 'purple' },
            { key: 'Follow-Up', color: 'pink' },
            { key: 'Closed', color: 'gray' },
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
    async loadLeads(page = 1) {
        try {
            this.currentPage = page;
            const tbody = document.getElementById('leads-table-body');
            tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-8 text-center text-gray-400"><i class="fas fa-spinner fa-spin mr-2"></i>Loading...</td></tr>';

            let url = `/api/pipeline/leads?page=${page}&per_page=15`;
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
        const tbody = document.getElementById('leads-table-body');
        if (!leads || leads.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-8 text-center text-gray-400">No leads found.</td></tr>';
            return;
        }

        tbody.innerHTML = leads.map(lead => {
            // Status Badge Logic
            let badgeClass = 'bg-gray-100 text-gray-600';
            const s = (lead.status || '').toLowerCase();
            if (s === 'new') badgeClass = 'bg-blue-50 text-blue-700 border border-blue-100';
            if (s === 'won') badgeClass = 'bg-green-50 text-green-700 border border-green-100';
            if (s === 'lost') badgeClass = 'bg-red-50 text-red-700 border border-red-100';
            if (s.includes('follow')) badgeClass = 'bg-pink-50 text-pink-700 border border-pink-100';

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
        const prevBtn = document.getElementById('prev-page-btn');
        const nextBtn = document.getElementById('next-page-btn');
        const label = document.getElementById('page-info');

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
    async loadAgents() {
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/pipeline/agents');
            if (resp && resp.ok) {
                const data = await resp.json();
                const tbody = document.getElementById('agent-table-body');
                if (!tbody) return;

                tbody.innerHTML = (data.agents || []).slice(0, 5).map(a => `
                    <tr class="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                        <td class="px-4 py-2 font-medium text-gray-800">${a.name}</td>
                        <td class="px-4 py-2 text-right text-gray-600">${a.calls_made}</td>
                        <td class="px-4 py-2 text-right font-medium text-green-600">${a.closed_leads}</td>
                    </tr>
                `).join('');
            }
        } catch (e) {
            console.error("Agents Error:", e);
        }
    }

    /* ------------------------------------------------
       4. Chart
    ------------------------------------------------ */
    renderChart(pipeline) {
        const ctx = document.getElementById('pipelineChart');
        if (!ctx) return;

        // Destroy old if exists? (Assuming single init for now)

        const dataValues = [
            pipeline['New'] || 0,
            pipeline['Attempted'] || 0,
            pipeline['Connected'] || 0,
            pipeline['Interested'] || 0,
            pipeline['Won'] || 0
        ];

        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['New', 'Attempted', 'Connected', 'Interested', 'Won'],
                datasets: [{
                    data: dataValues,
                    backgroundColor: ['#3b82f6', '#fbbf24', '#6366f1', '#a855f7', '#22c55e'],
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
}

window.pipelineManager = new PipelineManager();
