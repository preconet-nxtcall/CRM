class PipelineManager {
    constructor() {
        this.chart = null;
        this.currentPage = 1;
        this.pageSize = 10;
        this.currentStatus = 'all';

        // Bind functions
        this.nextPage = this.nextPage.bind(this);
        this.prevPage = this.prevPage.bind(this);
    }

    async init() {
        console.log("Pipeline Manager Initializing...");
        await this.loadStats();
        await this.loadLeads(1);
        await this.loadAgents();
        this.setupEventListeners();
    }

    setupEventListeners() {
        const nextBtn = document.getElementById('pl-next-page-btn');
        const prevBtn = document.getElementById('pl-prev-page-btn');
        if (nextBtn) nextBtn.onclick = this.nextPage;
        if (prevBtn) prevBtn.onclick = this.prevPage;
    }

    async loadStats() {
        try {
            const offset = new Date().getTimezoneOffset();
            const response = await auth.makeAuthenticatedRequest(`/api/pipeline/stats?timezone_offset=${offset}`);
            if (!response) return;
            const data = await response.json();

            if (data.kpis) {
                this.updateKPIs(data.kpis);
            }
            if (data.pipeline) {
                this.renderChart(data.pipeline);
                this.renderFunnel(data.pipeline);
                this.renderPipelineBar(data.pipeline);
            }
        } catch (error) {
            console.error('Pipeline Stats Error:', error);
        }
    }

    updateKPIs(kpis) {
        const mapping = {
            'kpi-total-leads': kpis.total_leads,
            'kpi-new-today': kpis.new_leads_today,
            'kpi-calls-today': kpis.calls_made_today,
            'kpi-connected': kpis.connected_calls_today,
            'kpi-conversion': kpis.conversion_rate + '%'
        };

        for (const [id, val] of Object.entries(mapping)) {
            const el = document.getElementById(id);
            if (el) el.textContent = val !== undefined ? val : '-';
        }
    }

    async loadLeads(page = 1) {
        try {
            this.currentPage = page;
            const offset = new Date().getTimezoneOffset();
            let url = `/api/pipeline/leads?page=${page}&per_page=${this.pageSize}&timezone_offset=${offset}`;
            if (this.currentStatus !== 'all') {
                url += `&status=${this.currentStatus}`;
            }

            const response = await auth.makeAuthenticatedRequest(url);
            if (!response) return;
            const data = await response.json();

            this.renderLeadsTable(data.leads || []);
            this.updatePagination(data.pagination);
        } catch (error) {
            console.error('Pipeline Leads Error:', error);
        }
    }

    renderLeadsTable(leads) {
        const tbody = document.getElementById('pipeline-leads-table-body');
        if (!tbody) return;

        if (leads.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="px-6 py-12 text-center text-gray-400">No leads found matching criteria.</td></tr>`;
            return;
        }

        tbody.innerHTML = leads.map(lead => `
            <tr class="hover:bg-gray-50 transition-colors border-b border-gray-50 last:border-0">
                <td class="px-6 py-4">
                    <div class="flex flex-col">
                        <span class="font-bold text-gray-900">${lead.name}</span>
                        <span class="text-xs text-gray-500">${lead.phone || '-'}</span>
                    </div>
                </td>
                <td class="px-6 py-4">
                    <span class="px-2 py-1 bg-gray-100 text-gray-600 rounded text-[10px] font-bold">${lead.source}</span>
                </td>
                <td class="px-6 py-4">
                    <span class="text-xs text-gray-600">${lead.agent}</span>
                </td>
                <td class="px-6 py-4">
                    <span class="px-2 py-1 rounded-full text-[10px] font-black uppercase ${this.getStatusColor(lead.status)}">
                        ${lead.status}
                    </span>
                </td>
                <td class="px-6 py-4 text-xs text-gray-500">
                    ${window.formatDateTime(lead.last_activity)}
                </td>
            </tr>
        `).join('');
    }

    updatePagination(pagination) {
        if (!pagination) return;
        const info = document.getElementById('pl-page-info');
        if (info) info.textContent = `Page ${pagination.current} of ${pagination.pages}`;

        const nextBtn = document.getElementById('pl-next-page-btn');
        const prevBtn = document.getElementById('pl-prev-page-btn');
        if (nextBtn) nextBtn.disabled = pagination.current >= pagination.pages;
        if (prevBtn) prevBtn.disabled = pagination.current <= 1;
    }

    nextPage() {
        this.loadLeads(this.currentPage + 1);
    }

    prevPage() {
        if (this.currentPage > 1) {
            this.loadLeads(this.currentPage - 1);
        }
    }

    async loadAgents() {
        try {
            const filter = document.getElementById('pipeline-agent-filter');
            const dateFilter = filter ? filter.value : 'month';
            const offset = new Date().getTimezoneOffset();
            const response = await auth.makeAuthenticatedRequest(`/api/pipeline/agents?date_filter=${dateFilter}&timezone_offset=${offset}`);
            if (!response) return;
            const data = await response.json();
            this.renderAgentsTable(data.agents || []);
        } catch (error) {
            console.error('Pipeline Agents Error:', error);
        }
    }

    renderAgentsTable(agents) {
        const tbody = document.getElementById('pipeline-agent-table-body');
        if (!tbody) return;

        tbody.innerHTML = agents.slice(0, 5).map(agent => `
            <tr class="border-b border-gray-50 last:border-0 hover:bg-gray-50 transition-colors">
                <td class="px-4 py-3 text-sm font-medium text-gray-900">${agent.name}</td>
                <td class="px-4 py-3 text-sm text-gray-600 text-right font-mono">${agent.calls_made}</td>
                <td class="px-4 py-3 text-sm font-bold text-brand-success text-right font-mono">${agent.closed_leads}</td>
            </tr>
        `).join('');
    }

    getStatusColor(status) {
        const s = status ? status.toLowerCase() : '';
        if (s.includes('won') || s.includes('closed') || s.includes('convert')) return 'bg-green-100 text-green-700';
        if (s.includes('lost') || s.includes('junk')) return 'bg-red-100 text-red-700';
        if (s.includes('new')) return 'bg-blue-100 text-blue-700';
        if (s.includes('attempt') || s.includes('follow')) return 'bg-amber-100 text-amber-700';
        if (s.includes('connect')) return 'bg-indigo-100 text-indigo-700';
        return 'bg-gray-100 text-gray-700';
    }

    /* ------------------------------------------------
       1. Doughnut Chart (All 7 Stages)
    ------------------------------------------------ */
    renderChart(pipeline) {
        const ctx = document.getElementById('pipelineChart');
        if (!ctx) return;

        if (this.chart) {
            this.chart.destroy();
        }

        const stages = ['New', 'Attempted', 'Connected', 'Follow-Up', 'Converted', 'Won', 'Lost'];
        const values = stages.map(s => pipeline[s] || 0);

        this.chart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: stages,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        '#3b82f6', // New (Blue)
                        '#f59e0b', // Attempted (Amber)
                        '#6366f1', // Connected (Indigo)
                        '#a855f7', // Follow-Up (Purple)
                        '#14b8a6', // Converted (Teal)
                        '#10b981', // Won (Emerald)
                        '#ef4444'  // Lost (Red)
                    ],
                    borderWidth: 0,
                    hoverOffset: 12
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            usePointStyle: true,
                            padding: 10,
                            font: { family: 'Inter', size: 10 },
                            boxWidth: 8
                        }
                    }
                }
            }
        });
    }

    /* ------------------------------------------------
       2. Sales Funnel - 7 Stage 3D Design
    ------------------------------------------------ */
    renderFunnel(pipeline) {
        const container = document.getElementById('funnel-container');
        if (!container) return;

        const stages = [
            { key: 'New', color: 'from-blue-600 to-blue-400', top: 100, bottom: 90, icon: 'fa-bullhorn', label: 'AWARENESS', desc: 'New Leads' },
            { key: 'Attempted', color: 'from-amber-500 to-amber-400', top: 90, bottom: 80, icon: 'fa-phone-alt', label: 'INTEREST', desc: 'Outreach' },
            { key: 'Connected', color: 'from-indigo-600 to-indigo-500', top: 80, bottom: 70, icon: 'fa-comments', label: 'ENGAGEMENT', desc: 'Contacted' },
            { key: 'Follow-Up', color: 'from-purple-600 to-purple-400', top: 70, bottom: 60, icon: 'fa-calendar-check', label: 'NURTURING', desc: 'Call Backs' },
            { key: 'Converted', color: 'from-teal-500 to-teal-400', top: 60, bottom: 50, icon: 'fa-check-double', label: 'INTENT', desc: 'Qualified' },
            { key: 'Won', color: 'from-emerald-500 to-emerald-400', top: 50, bottom: 40, icon: 'fa-trophy', label: 'PURCHASE', desc: 'Closed Won' },
            { key: 'Lost', color: 'from-red-600 to-red-400', top: 40, bottom: 40, icon: 'fa-times-circle', label: 'CLOSED LOST', desc: 'Lost Deals' }
        ];

        container.innerHTML = `
            <div class="w-full flex gap-4 mt-2">
                <!-- Left Labels -->
                <div class="flex flex-col flex-shrink-0 gap-1" style="width: 100px;">
                    ${stages.map(s => `
                        <div class="h-[60px] flex flex-col justify-center">
                            <h4 class="text-[8px] font-black text-blue-500 opacity-70 tracking-tighter uppercase whitespace-nowrap">${s.label}</h4>
                            <p class="text-[10px] font-semibold text-gray-500 leading-tight">${s.desc}</p>
                        </div>
                    `).join('')}
                </div>

                <!-- Funnel Shapes -->
                <div class="flex-1 flex flex-col items-center min-w-0">
                    ${stages.map((stage, index) => {
            const count = pipeline[stage.key] || 0;
            const t1 = (100 - stage.top) / 2;
            const t2 = 100 - t1;
            const b1 = (100 - stage.bottom) / 2;
            const b2 = 100 - b1;

            return `
                            <div class="relative w-full -mb-1 group cursor-default h-[60px]">
                                <div class="absolute inset-0 bg-gradient-to-r ${stage.color} shadow-lg transition-all duration-300 transform group-hover:scale-[1.02] active:scale-[0.98]"
                                     style="clip-path: polygon(${t1}% 0%, ${t2}% 0%, ${b2}% 100%, ${b1}% 100%); z-index: ${10 - index};">
                                    <div class="absolute inset-0 opacity-20 bg-gradient-to-b from-white to-transparent h-[4px]"></div>
                                    <div class="h-full flex items-center justify-between px-[15%] text-white">
                                        <div class="flex items-center gap-2">
                                            <i class="fas ${stage.icon} text-xs opacity-80"></i>
                                            <span class="text-[11px] font-black tracking-wide">${stage.key}</span>
                                        </div>
                                        <div class="bg-white bg-opacity-20 backdrop-blur-md px-2 py-0.5 rounded-full border border-white border-opacity-30">
                                            <span class="text-[10px] font-black">${count.toLocaleString()}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
        }).join('')}
                </div>
            </div>
        `;
    }

    /* ------------------------------------------------
       3. Horizontal Pipeline Bar (7 Stages)
    ------------------------------------------------ */
    renderPipelineBar(pipeline) {
        const container = document.getElementById('pipeline-container');
        if (!container) return;

        const stages = [
            { key: 'New', label: 'New', color: 'blue', icon: 'fa-star' },
            { key: 'Attempted', label: 'Attempted', color: 'amber', icon: 'fa-phone-alt' },
            { key: 'Connected', label: 'Connected', color: 'indigo', icon: 'fa-comments' },
            { key: 'Follow-Up', label: 'Follow-Up', color: 'purple', icon: 'fa-calendar-check' },
            { key: 'Converted', label: 'Converted', color: 'teal', icon: 'fa-check-double' },
            { key: 'Won', label: 'Won', color: 'emerald', icon: 'fa-trophy' },
            { key: 'Lost', label: 'Lost', color: 'red', icon: 'fa-times-circle' }
        ];

        container.innerHTML = stages.map(s => {
            const count = pipeline[s.key] || 0;
            const isActive = this.currentStatus === s.key;
            return `
                <div class="flex-1 min-w-[130px] px-3 py-3 cursor-pointer hover:bg-gray-50 transition-colors border-r border-gray-100 last:border-0 group ${isActive ? 'bg-blue-50' : ''}"
                     onclick="pipelineManager.filterByStatus('${s.key}')">
                    <div class="flex items-center gap-2 mb-1">
                        <div class="w-1.5 h-1.5 rounded-full bg-${s.color}-500 group-hover:scale-125 transition-transform"></div>
                        <span class="text-[9px] font-bold text-gray-400 uppercase tracking-tight">${s.label}</span>
                    </div>
                    <div class="flex items-center justify-between">
                        <span class="text-lg font-black text-gray-900">${count.toLocaleString()}</span>
                        <i class="fas ${s.icon} text-gray-200 text-[10px] group-hover:text-${s.color}-400 transition-colors"></i>
                    </div>
                </div>
            `;
        }).join('');
    }

    async filterByStatus(status) {
        console.log("Filtering pipeline by status:", status);
        this.currentStatus = status;

        // Update Label
        const label = document.getElementById('current-filter-label');
        if (label) label.textContent = (status === 'all' ? 'All' : status) + ' Leads';

        // Reload data
        await this.loadLeads(1);
        await this.loadStats(); // Update visuals
    }
}

// Global scope initialization
window.pipelineManager = new PipelineManager();
