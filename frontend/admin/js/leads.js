class LeadsManager {
    constructor() {
        this.tableBody = document.getElementById('leadsTableBody');
        this.mobileContainer = document.getElementById('leadsMobileCards');
        this.paginationContainer = document.getElementById('leadsPagination');
        this.itemsPerPage = 10; // Changed to 10 records per page
        this.currentFilter = 'all'; // Default filter (Source)
        this.statusFilter = 'all'; // New Status Filter
        this.dateFilter = 'all'; // Default to all records

        // New Filters
        this.searchQuery = '';
        this.start_date = null;
        this.end_date = null;
        this.agents = []; // Prevent undefined map error
    }

    async init() {
        // Called when view switches to 'sectionLeads'
        this.initSearch();
        this.loadAgents(); // Load Agents for dropdown
        await this.loadLeads();
    }

    filterLeads(source) {
        this.currentFilter = source;
        this.updateFilterButtons();
        this.loadLeads(1); // Reset to page 1
    }

    changeStatusFilter(val) {
        this.statusFilter = val;
        this.loadLeads(1);
    }

    changeDateFilter(val) {
        console.log("Changing Date Filter:", val);
        this.dateFilter = val;

        const today = new Date();
        const formatDate = (d) => {
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        };

        if (val === 'today') {
            this.start_date = formatDate(today);
            this.end_date = formatDate(today);
        } else if (val === 'week') {
            const lastWeek = new Date(today);
            lastWeek.setDate(today.getDate() - 7);
            this.start_date = formatDate(lastWeek);
            this.end_date = formatDate(today);
        } else if (val === 'month') {
            const lastMonth = new Date(today);
            lastMonth.setDate(today.getDate() - 30);
            this.start_date = formatDate(lastMonth);
            this.end_date = formatDate(today);
        } else {
            // All Time
            this.start_date = null;
            this.end_date = null;
        }

        console.log(`New Date Range: ${this.start_date} to ${this.end_date}`);

        // Reset Custom Inputs UI
        const customInput = document.getElementById('leadsDateFilter');
        if (customInput) customInput.value = '';

        const todayBtn = document.getElementById('btn-leads-today');
        if (todayBtn) todayBtn.classList.remove('bg-blue-50', 'text-blue-600', 'border-blue-300');

        this.loadLeads(1);
    }


    updateFilterButtons() {
        // Reset all buttons
        const types = ['all', 'facebook', 'indiamart', 'magicbricks', '99acres', 'justdial', 'housing'];
        types.forEach(type => {
            const btn = document.getElementById(`btn-filter-${type}`);
            if (btn) {
                // Base classes for both states (pill structure)
                const baseClass = "px-4 py-1.5 text-sm font-medium rounded-full transition-all border ";

                if (type === this.currentFilter) {
                    // Active State: Blue Pill
                    btn.className = baseClass + "bg-blue-50 text-blue-700 border-blue-100 shadow-sm";
                } else {
                    // Inactive State: Gray Text, Transparent Border
                    btn.className = baseClass + "text-gray-600 bg-white border-transparent hover:bg-gray-50 hover:border-gray-200";
                }
            }
        });
    }

    async loadAgents() {
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/pipeline/agents');
            if (resp && resp.ok) {
                const data = await resp.json();
                this.agents = data.agents || [];
            }
        } catch (e) { console.warn("Agents load warning", e); }
    }

    renderAgentOptions(assignedId) {
        if (!this.agents || this.agents.length === 0) return '';
        return this.agents.map(agent =>
            `<option value="${agent.id}" ${parseInt(assignedId) === parseInt(agent.id) ? 'selected' : ''}>${agent.name}</option>`
        ).join('');
    }

    async loadLeads(page = 1) {
        if (!this.tableBody) return;

        this.currentPage = page;
        this.showLoading(); // Use Skeleton Loader


        try {
            // Include Filter in Request - now with date filter
            // let url = `/api/facebook/leads?page=${page}&per_page=${this.itemsPerPage}&date_filter=${this.dateFilter}`;
            // Switched to pipeline endpoint for search support
            let url = `/api/pipeline/leads?page=${page}&per_page=${this.itemsPerPage}`;

            if (this.currentFilter !== 'all') {
                url += `&source=${this.currentFilter}`;
            }

            if (this.statusFilter !== 'all') {
                url += `&status=${this.statusFilter}`;
            }

            // Add Search
            if (this.searchQuery) {
                url += `&search=${encodeURIComponent(this.searchQuery)}`;
            }

            // Add Date Filters
            if (this.start_date) url += `&start_date=${this.start_date}`;
            if (this.end_date) url += `&end_date=${this.end_date}`;

            // Add Timezone Offset for accurate date filtering
            const offset = new Date().getTimezoneOffset();
            url += `&timezone_offset=${offset}`;

            const resp = await auth.makeAuthenticatedRequest(url);
            if (resp && resp.ok) {
                const data = await resp.json();
                console.log("Leads Data:", data); // DEBUG
                this.leads = data.leads; // STORE LEADS LOCALLY
                this.renderTable(data.leads);
                // Backend now returns flat pagination structure or nested
                // We standardized on flattened keys in pipeline.py: current_page, pages, total_leads
                this.renderPagination(data.current_page || data.pagination?.current, data.pages || data.pagination?.pages);
            } else {
                let errorMsg = "Failed to load leads";
                try {
                    const errData = await resp.json();
                    if (errData.error) errorMsg = errData.error;
                } catch (e) { }
                if (this.tableBody) this.tableBody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-red-500">${errorMsg}</td></tr>`;
                if (this.mobileContainer) this.mobileContainer.innerHTML = `<div class="text-center py-8 text-red-500">${errorMsg}</div>`;
            }
        } catch (e) {
            console.error("Error loading leads", e);
            if (this.tableBody) this.tableBody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-red-500">Error: ${e.message}</td></tr>`;
            if (this.mobileContainer) this.mobileContainer.innerHTML = `<div class="text-center py-8 text-red-500">Error: ${e.message}</div>`;
        }
    }


    showLoading() {
        // Table Skeleton Row
        const skeletonRow = `
            <tr class="animate-pulse border-b border-gray-50 last:border-0">
                <td class="px-6 py-4 whitespace-nowrap">
                     <div class="h-3 bg-gray-200 rounded w-16 mb-1"></div>
                     <div class="h-2 bg-gray-100 rounded w-12"></div>
                </td>
                <td class="px-6 py-4">
                     <div class="h-3 bg-gray-200 rounded w-24 mb-1"></div>
                     <div class="h-3 bg-gray-100 rounded w-20"></div>
                </td>
                <td class="px-6 py-4">
                     <div class="h-3 bg-gray-100 rounded w-32"></div>
                </td>
                <td class="px-6 py-4">
                     <div class="h-5 w-20 bg-gray-100 rounded-lg"></div>
                </td>
                <td class="px-6 py-4">
                     <div class="h-3 bg-gray-200 rounded w-24 mb-1"></div>
                     <div class="h-2 bg-gray-100 rounded w-16"></div>
                </td>
                <td class="px-6 py-4">
                    <div class="h-4 bg-gray-100 rounded w-20"></div>
                </td>
                <td class="px-6 py-4">
                     <div class="h-5 w-20 bg-gray-100 rounded-full"></div>
                </td>
                 <td class="px-6 py-4 text-right">
                    <div class="flex justify-end gap-2">
                         <div class="h-8 w-8 bg-gray-100 rounded-full"></div>
                         <div class="h-8 w-8 bg-gray-100 rounded-full"></div>
                    </div>
                </td>
            </tr>
        `;

        if (this.tableBody) {
            this.tableBody.innerHTML = skeletonRow.repeat(5);
        }

        if (this.mobileContainer) {
            this.mobileContainer.innerHTML = '<div class="p-4 space-y-4 animate-pulse">' +
                '<div class="h-24 bg-gray-100 rounded-lg"></div>'.repeat(3) +
                '</div>';
        }
    }

    renderLeadDetails(lead) {
        if (!lead.custom_fields) return '-';
        const source = (lead.source || '').toLowerCase();

        if (source === 'indiamart') {
            // IndiaMART Format
            const subject = lead.custom_fields.subject || 'Inquiry';
            const company = lead.custom_fields.company || '';
            const message = lead.custom_fields.message || '';

            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${subject}">${subject}</div>
                <div class="text-blue-600 font-medium truncate max-w-[200px]" title="${company}">${company}</div>
                ${message ? `<div class="text-[10px] text-gray-400 mt-1 truncate max-w-[200px]" title="${message}">${message}</div>` : ''}
            `;
        } else if (source === 'call_history') {
            // Call History Format
            return `<div class="text-gray-500 italic">Manual Entry</div>`;

        } else if (source === 'magicbricks') {
            // Magicbricks Format
            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${lead.property_type}">${lead.property_type || '-'}</div>
                <div class="text-gray-500 truncate max-w-[200px]" title="${lead.budget} | ${lead.location}">${lead.budget || '-'}</div>
            `;
        } else if (source === '99acres') {
            // 99acres Format

            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${lead.property_type}">${lead.property_type || '-'}</div>
                <div class="text-gray-500 truncate max-w-[200px]" title="${lead.location}">${lead.location || '-'}</div>
            `;
        } else if (source === 'justdial') {
            // JustDial Format
            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${lead.requirement}">${lead.requirement || 'Business Enquiry'}</div>
                <div class="text-gray-500 truncate max-w-[200px]" title="${lead.location}">${lead.location || '-'}</div>
            `;
        } else if (source === 'housing') {
            // Housing Format
            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${lead.requirement}">${lead.requirement || 'Residential Property'}</div>
                <div class="text-gray-500 truncate max-w-[200px]" title="${lead.budget || '-'}">${lead.budget || '-'}</div>
            `;
        } else if (source === 'manual') {
            // Manual Entry Format
            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${lead.requirement}">${lead.requirement || lead.property_type || 'Manual Entry'}</div>
                <div class="text-gray-500 truncate max-w-[200px]" title="${lead.location}">${lead.location || '-'}</div>
            `;
        } else {
            // Facebook / Default Format
            const campaign = lead.custom_fields.campaign_name;
            const ad = lead.custom_fields.ad_name;

            if (!campaign && !ad) return '-';

            return `
                ${campaign ? `<div class="font-bold text-gray-900 truncate max-w-[200px]" title="${campaign}">${campaign}</div>` : ''}
                ${ad ? `<div class="text-gray-500 truncate max-w-[200px]" title="${ad}">${ad}</div>` : ''}
            `;
        }
    }

    openLeadModal(leadId) {
        const lead = this.leads.find(l => l.id === leadId);
        if (!lead) {
            console.error("Lead not found for ID:", leadId);
            return;
        }

        const modal = document.getElementById('lead-details-modal');
        const content = document.getElementById('lead-details-content');

        let detailsHtml = '';
        const custom = lead.custom_fields || {};
        const source = (lead.source || '').toLowerCase();

        if (source === 'indiamart') {
            detailsHtml = `
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="block text-gray-500 text-xs">Sender Name</span>
                        <span class="font-medium text-gray-900">${lead.name || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Mobile</span>
                        <span class="font-medium text-gray-900">${lead.phone || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Email</span>
                        <span class="font-medium text-gray-900">${lead.email || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Company</span>
                        <span class="font-medium text-blue-600">${custom.company || '-'}</span>
                    </div>
                    <div class="col-span-2">
                        <span class="block text-gray-500 text-xs">Subject</span>
                        <span class="font-bold text-gray-900">${custom.subject || '-'}</span>
                    </div>
                    <div class="col-span-2 bg-gray-50 p-3 rounded max-h-60 overflow-y-auto">
                        <span class="block text-gray-500 text-xs mb-1">Message</span>
                        <p class="text-gray-700 whitespace-pre-wrap leading-relaxed">${custom.message || '-'}</p>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">City</span>
                        <span class="font-medium text-gray-900">${custom.city || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">State</span>
                        <span class="font-medium text-gray-900">${custom.state || '-'}</span>
                    </div>
                    <div class="col-span-2 border-t pt-2 mt-2">
                        <span class="block text-gray-500 text-xs">Unique Query ID</span>
                        <code class="text-xs bg-gray-100 px-2 py-1 rounded">${custom.indiamart_id || '-'}</code>
                    </div>
                </div>
             `;
        } else if (source === 'magicbricks') {
            // Magicbricks Format
            detailsHtml = `
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="block text-gray-500 text-xs">Sender Name</span>
                        <span class="font-medium text-gray-900">${lead.name || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Mobile</span>
                        <span class="font-medium text-gray-900">${lead.phone || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Email</span>
                        <span class="font-medium text-gray-900">${lead.email || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Property Type</span>
                        <span class="font-medium text-red-600">${lead.property_type || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Location</span>
                        <span class="font-medium text-gray-900">${lead.location || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Budget</span>
                        <span class="font-medium text-gray-900">${lead.budget || '-'}</span>
                    </div>
                    <div class="col-span-2 bg-gray-50 p-3 rounded max-h-60 overflow-y-auto">
                        <span class="block text-gray-500 text-xs mb-1">Requirement</span>
                        <p class="text-gray-700 whitespace-pre-wrap leading-relaxed">${lead.requirement || '-'}</p>
                    </div>
                </div>

            `;
        } else if (source === '99acres') {
            // 99acres Format
            detailsHtml = `
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="block text-gray-500 text-xs">Sender Name</span>
                        <span class="font-medium text-gray-900">${lead.name || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Mobile</span>
                        <span class="font-medium text-gray-900">${lead.phone || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Email</span>
                        <span class="font-medium text-gray-900">${lead.email || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Property Type</span>
                        <span class="font-medium text-blue-600">${lead.property_type || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Location</span>
                        <span class="font-medium text-gray-900">${lead.location || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Project</span>
                        <span class="font-medium text-gray-900">${lead.custom_fields?.project || '-'}</span>
                    </div>

                </div>
            `;
        } else if (source === 'facebook') {
            // Facebook Format (Enhanced)
            detailsHtml = `
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="block text-gray-500 text-xs">Lead Name</span>
                        <span class="font-medium text-gray-900">${lead.name || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Phone</span>
                        <span class="font-medium text-gray-900">${lead.phone || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Email</span>
                        <span class="font-medium text-gray-900">${lead.email || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Form Name</span>
                        <span class="font-medium text-blue-600 break-words">${custom.form_name || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Campaign</span>
                        <span class="font-medium text-gray-700 break-words">${custom.campaign_name || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Ad Name</span>
                        <span class="font-medium text-gray-700 break-words">${custom.ad_name || '-'}</span>
                    </div>
                    <div class="col-span-2 bg-gray-50 p-3 rounded">
                        <span class="block text-gray-500 text-xs mb-2">Additional Data</span>
                         <div class="grid grid-cols-2 gap-2">
                            ${Object.entries(custom).map(([key, value]) => {
                if (['form_name', 'campaign_name', 'ad_name'].includes(key)) return ''; // Skip already shown fields
                return `
                                <div>
                                    <span class="block text-[10px] text-gray-400 uppercase">${key.replace(/_/g, ' ')}</span>
                                    <span class="text-xs text-gray-700 break-words">${value}</span>
                                </div>
                            `}).join('')}
                         </div>
                    </div>
                </div>
            `;
        } else if (source === 'justdial') {
            // JustDial Format
            detailsHtml = `
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="block text-gray-500 text-xs">Sender Name</span>
                        <span class="font-medium text-gray-900">${lead.name || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Mobile</span>
                        <span class="font-medium text-gray-900">${lead.phone || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Email</span>
                        <span class="font-medium text-gray-900">${lead.email || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Category</span>
                        <span class="font-medium text-blue-600">${lead.requirement || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Location</span>
                        <span class="font-medium text-gray-900">${lead.location || '-'}</span>
                    </div>
                    <div class="col-span-2 border-t pt-2 mt-2">
                        <span class="block text-gray-500 text-xs">Raw Subject</span>
                         <span class="text-xs text-gray-500">${lead.custom_fields?.raw_subject || '-'}</span>
                    </div>
                </div>

            `;
        } else if (source === 'housing') {
            // Housing Format
            detailsHtml = `
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="block text-gray-500 text-xs">Sender Name</span>
                        <span class="font-medium text-gray-900">${lead.name || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Mobile</span>
                        <span class="font-medium text-gray-900">${lead.phone || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Email</span>
                        <span class="font-medium text-gray-900">${lead.email || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Project/Requirement</span>
                        <span class="font-medium text-purple-600">${lead.requirement || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Location</span>
                        <span class="font-medium text-gray-900">${lead.location || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Budget</span>
                        <span class="font-medium text-gray-900">${lead.budget || '-'}</span>
                    </div>
                </div>
            `;
        } else if (source === 'manual') {
            // Manual Entry Format
            detailsHtml = `
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="block text-gray-500 text-xs">Lead Name</span>
                        <span class="font-medium text-gray-900">${lead.name || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Phone</span>
                        <span class="font-medium text-gray-900">${lead.phone || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Email</span>
                        <span class="font-medium text-gray-900">${lead.email || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Property Type</span>
                        <span class="font-medium text-blue-600">${lead.property_type || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Location</span>
                        <span class="font-medium text-gray-900">${lead.location || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Budget</span>
                        <span class="font-medium text-gray-900">${lead.budget || '-'}</span>
                    </div>
                    <div class="col-span-2 bg-gray-50 p-3 rounded max-h-60 overflow-y-auto">
                        <span class="block text-gray-500 text-xs mb-1">Requirement</span>
                        <p class="text-gray-700 whitespace-pre-wrap leading-relaxed">${lead.requirement || '-'}</p>
                    </div>
                </div>
            `;
        } else {
            // Generic Fallback (SaaS Style)
            detailsHtml = `
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="block text-gray-500 text-xs">Lead Name</span>
                        <span class="font-medium text-gray-900">${lead.name || '-'}</span>
                    </div>
                    <div>
                        <span class="block text-gray-500 text-xs">Phone</span>
                        <span class="font-medium text-gray-900">${lead.phone || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Email</span>
                        <span class="font-medium text-gray-900">${lead.email || '-'}</span>
                    </div>
                     <div>
                        <span class="block text-gray-500 text-xs">Date</span>
                        <span class="font-medium text-gray-900">${new Date(lead.created_at).toLocaleDateString()}</span>
                    </div>
                    <div class="col-span-2 bg-gray-50 p-3 rounded">
                        <span class="block text-gray-500 text-xs mb-2">Additional Data</span>
                         <div class="grid grid-cols-2 gap-2">
                            ${Object.entries(custom).map(([key, value]) => `
                                <div>
                                    <span class="block text-[10px] text-gray-400 uppercase">${key.replace(/_/g, ' ')}</span>
                                    <span class="text-xs text-gray-700 break-words">${value}</span>
                                </div>
                            `).join('')}
                         </div>
                    </div>
                </div>
             `;
        }

        content.innerHTML = detailsHtml;
        modal.classList.remove('hidden');
    }

    renderTable(leads) {
        if (!leads || leads.length === 0) {
            if (this.tableBody) this.tableBody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-gray-500">No leads found.</td></tr>`;
            if (this.mobileContainer) this.mobileContainer.innerHTML = `<div class="text-center py-12 text-gray-500 bg-gray-50 rounded-lg border border-dashed border-gray-200 m-4">No leads found.</div>`;
            return;
        }

        // 1. Desktop Table Rows
        if (this.tableBody) {
            this.tableBody.innerHTML = leads.map(lead => {
                // Enhanced Date Formatting (Local Time, Cleaner)
                let dateStr = lead.created_at;
                if (dateStr && !dateStr.endsWith('Z')) dateStr += 'Z';
                const dateObj = new Date(dateStr);

                // Split Date and Time for 2-line display
                const datePart = dateObj.toLocaleDateString('en-IN', {
                    day: '2-digit', month: 'short', year: 'numeric'
                });
                const timePart = dateObj.toLocaleTimeString('en-IN', {
                    hour: '2-digit', minute: '2-digit', hour12: true
                });
                const dateHtml = `<div class="font-medium text-gray-900">${datePart}</div><div class="text-gray-500 text-[10px]">${timePart}</div>`;

                let statusColor = "bg-gray-100 text-gray-800";
                if (lead.status === 'new') statusColor = "bg-blue-100 text-blue-800";
                if (lead.status === 'attempted') statusColor = "bg-yellow-100 text-yellow-800";
                if (lead.status === 'converted') statusColor = "bg-indigo-100 text-indigo-800";
                if (lead.status === 'interested') statusColor = "bg-purple-100 text-purple-800";
                if (lead.status === 'follow-up') statusColor = "bg-pink-100 text-pink-800";
                if (lead.status === 'won') statusColor = "bg-green-100 text-green-800";
                if (lead.status === 'lost') statusColor = "bg-red-100 text-red-800";

                const source = (lead.source || '').toLowerCase();
                let sourceBadge = `<span class="px-2 py-0.5 text-xs font-bold rounded bg-gray-100 text-gray-700 border border-gray-200">${lead.source ? lead.source.toUpperCase() : 'UNKNOWN'}</span>`;

                // Badge Logic (Same as before)
                if (source === 'magicbricks') sourceBadge = `<span class="px-2 py-0.5 text-xs font-bold rounded bg-[#FFF0F0] text-[#D8232A] border border-[#ffdbdb]">MAGICBRICKS</span>`;
                else if (source === '99acres') sourceBadge = `<span class="px-2 py-0.5 text-xs font-bold rounded bg-[#F0F8FF] text-[#005CA8] border border-[#dceeff]">99ACRES</span>`;
                else if (source === 'housing') sourceBadge = `<span class="px-2 py-0.5 text-xs font-bold rounded bg-[#FAF0FA] text-[#800080] border border-[#f5d6f5]">HOUSING</span>`;
                else if (source === 'indiamart') sourceBadge = `<span class="px-2 py-0.5 text-xs font-bold rounded bg-[#EEF2FF] text-[#4338CA] border border-[#e0e7ff]">INDIAMART</span>`;
                else if (source === 'justdial') sourceBadge = `<span class="px-2 py-0.5 text-xs font-bold rounded bg-[#FFF7ED] text-[#EA580C] border border-[#ffedd5]">JUSTDIAL</span>`;
                else if (source === 'facebook') sourceBadge = `<span class="px-2 py-0.5 text-xs font-bold rounded bg-[#EFF6FF] text-[#1877F2] border border-[#dbeafe]">FACEBOOK</span>`;
                else if (source === 'call_history') sourceBadge = `<span class="px-2 py-0.5 text-xs font-bold rounded bg-gray-100 text-gray-700 border border-gray-200">CALL HISTORY</span>`;

                return `
                    <tr class="hover:bg-gray-50 transition-colors">
                        <td class="px-4 py-3 whitespace-nowrap text-xs">${dateHtml}</td>
                        <td class="px-4 py-3 whitespace-nowrap">
                            <div class="font-medium text-gray-900">${lead.name || '-'}</div>
                            <div class="text-xs text-blue-600 custom-copy-text cursor-pointer hover:underline mt-0.5" 
                                 onclick="leadsManager.showCallHistory('${lead.phone}')" 
                                 title="Click to view call history">
                                 ${lead.phone || '-'}
                            </div>
                        </td>
                        <td class="px-4 py-3 text-gray-500 whitespace-nowrap">${lead.email || '-'}</td>
                        <td class="px-4 py-3">${sourceBadge}</td>
                        <td class="px-4 py-3 leading-tight">${this.renderLeadDetails(lead)}</td>
                        <td class="px-4 py-3 text-gray-600">
                             <select onchange="leadsManager.updateLeadAgent(${lead.id}, this.value)" 
                                class="text-xs rounded border-gray-200 shadow-sm focus:border-blue-500 focus:ring focus:ring-blue-200 focus:ring-opacity-50 bg-white">
                                <option value="">Unassigned</option>
                                ${this.renderAgentOptions(lead.assigned_agent_id)}
                            </select>
                        </td>
                        <td class="px-4 py-3">
                             <select onchange="leadsManager.updateLeadStatus(${lead.id}, this.value)" 
                                class="text-xs rounded border-gray-200 shadow-sm focus:border-blue-500 focus:ring focus:ring-blue-200 focus:ring-opacity-50 ${statusColor}">
                                <option value="new" ${lead.status === 'new' ? 'selected' : ''}>New</option>
                                <option value="attempted" ${lead.status === 'attempted' ? 'selected' : ''}>Attempted</option>
                                <option value="interested" ${lead.status === 'interested' ? 'selected' : ''}>Interested</option>
                                <option value="follow-up" ${lead.status === 'follow-up' ? 'selected' : ''}>Follow-Up</option>
                                <option value="converted" ${lead.status === 'converted' ? 'selected' : ''}>Converted</option>
                                <option value="won" ${lead.status === 'won' ? 'selected' : ''}>Won</option>
                                <option value="lost" ${lead.status === 'lost' ? 'selected' : ''}>Lost</option>
                            </select>
                        </td>
                        <td class="px-4 py-3 whitespace-nowrap text-sm font-medium text-right">
                            <button onclick="leadsManager.openLeadModal(${lead.id})" 
                                    class="p-1.5 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors mr-1" title="View Details">
                                    <i class="fas fa-eye"></i>
                            </button>
                            <button onclick="leadsManager.showHistory(${lead.id})" 
                                    class="p-1.5 text-purple-600 hover:text-purple-800 hover:bg-purple-50 rounded transition-colors" title="History & Status">
                                    <i class="fas fa-history"></i>
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        // 2. Mobile Cards
        if (this.mobileContainer) {
            this.mobileContainer.innerHTML = leads.map(lead => {
                let dateStr = lead.created_at;
                if (dateStr && !dateStr.endsWith('Z')) dateStr += 'Z';
                const dateObj = new Date(dateStr);
                const dateDisplay = dateObj.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) + ' ' +
                    dateObj.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });


                // Source Badge Small
                const source = (lead.source || '').toLowerCase();
                let sourceClass = "bg-gray-100 text-gray-700 border-gray-200";
                if (source === 'indiamart') sourceClass = "bg-[#EEF2FF] text-[#4338CA] border-[#e0e7ff]";
                else if (source === 'magicbricks') sourceClass = "bg-[#FFF0F0] text-[#D8232A] border-[#ffdbdb]";
                else if (source === 'facebook') sourceClass = "bg-[#EFF6FF] text-[#1877F2] border-[#dbeafe]";

                // Status Color for Card
                let statusColor = "bg-gray-100 text-gray-800";
                if (lead.status === 'new') statusColor = "bg-blue-100 text-blue-800";
                if (lead.status === 'converted') statusColor = "bg-green-100 text-green-800";
                if (lead.status === 'lost') statusColor = "bg-red-100 text-red-800";

                return `
                    <div class="p-4 bg-white hover:bg-gray-50 transition-colors">
                        <div class="flex justify-between items-start mb-2">
                             <div>
                                <h4 class="font-bold text-gray-900">${lead.name || 'Unknown'}</h4>
                                <div class="text-sm text-blue-600 font-medium mt-0.5" onclick="leadsManager.showCallHistory('${lead.phone}')">${lead.phone || '-'}</div>
                             </div>
                             <div class="text-xs text-gray-400 text-right">
                                <div>${dateDisplay}</div>
                                <span class="inline-block mt-1 px-2 py-0.5 text-[10px] uppercase font-bold border rounded ${sourceClass}">${lead.source || 'UNK'}</span>
                             </div>
                        </div>

                        <div class="flex items-center justify-between gap-3 mt-3 pt-3 border-t border-gray-50">
                             <div class="flex-1">
                                <select onchange="leadsManager.updateLeadStatus(${lead.id}, this.value)" 
                                    class="w-full text-xs py-1.5 pl-2 pr-6 rounded border-gray-200 font-medium ${statusColor}">
                                    <option value="new" ${lead.status === 'new' ? 'selected' : ''}>New</option>
                                    <option value="attempted" ${lead.status === 'attempted' ? 'selected' : ''}>Attempted</option>
                                    <option value="interested" ${lead.status === 'interested' ? 'selected' : ''}>Interested</option>
                                    <option value="follow-up" ${lead.status === 'follow-up' ? 'selected' : ''}>Follow-Up</option>
                                    <option value="converted" ${lead.status === 'converted' ? 'selected' : ''}>Converted</option>
                                    <option value="won" ${lead.status === 'won' ? 'selected' : ''}>Won</option>
                                    <option value="lost" ${lead.status === 'lost' ? 'selected' : ''}>Lost</option>
                                </select>
                             </div>
                             
                             <div class="flex gap-1">
                                <button onclick="leadsManager.openLeadModal(${lead.id})" class="p-2 text-gray-400 hover:text-blue-600 bg-gray-50 rounded-lg">
                                    <i class="fas fa-eye"></i>
                                </button>
                                 <button onclick="leadsManager.showHistory(${lead.id})" class="p-2 text-gray-400 hover:text-purple-600 bg-gray-50 rounded-lg">
                                    <i class="fas fa-history"></i>
                                </button>
                             </div>
                        </div>
                        
                        <div class="mt-2" onclick="event.stopPropagation()">
                             <select onchange="leadsManager.updateLeadAgent(${lead.id}, this.value)" 
                                class="w-full text-xs text-gray-500 py-1 pl-0 border-0 bg-transparent focus:ring-0">
                                <option value="">+ Assign Agent</option>
                                ${this.renderAgentOptions(lead.assigned_agent_id)}
                            </select>
                        </div>
                    </div>
                 `;
            }).join('');
        }
    }

    renderStatusOptions(currentStatus) {
        // Matched with Kanban Columns Key -> Label
        const statusLabels = {
            'new': 'Awareness',
            'attempted': 'Attempted',
            'converted': 'Converted',
            'won': 'Purchase',
            'lost': 'Lost' // "Lost" is usually good as is
        };
        const statuses = ['new', 'attempted', 'converted', 'won', 'lost'];

        return statuses.map(s => `
            <option value="${s}" ${s === currentStatus ? 'selected' : ''}>${statusLabels[s] || s}</option>
        `).join('');
    }

    async updateLeadStatus(leadId, newStatus) {
        try {
            const resp = await auth.makeAuthenticatedRequest(`/api/facebook/leads/${leadId}/status`, {
                method: 'PUT',
                body: JSON.stringify({ status: newStatus })
            });

            if (resp && resp.ok) {
                // Optional: Show toast or just reload
                // For smoother UX, maybe just leave it as is if successful
                // But reloading ensures consistency
                // Dispatch event for other components (Kanban)
                const event = new CustomEvent('leadStatusUpdated', { detail: { leadId, newStatus } });
                window.dispatchEvent(event);

                this.loadLeads(this.currentPage || 1);
            } else {
                alert("Failed to update status");
                this.loadLeads(this.currentPage || 1); // Revert UI
            }
        } catch (e) {
            console.error("Error updating status", e);
            alert("Error updating status");
        }
    }

    getStatusColor(status) {
        const s = (status || '').toLowerCase();

        if (s === 'new') return 'bg-blue-50 text-blue-700 ring-blue-600/20';

        // Attempted Group (Yellow) - Now includes Connected/Contacted
        if (['attempted', 'ringing', 'busy', 'not reachable', 'switch off', 'no answer', 'connected', 'contacted', 'in conversation'].includes(s))
            return 'bg-yellow-50 text-yellow-800 ring-yellow-600/20';

        // Interested Group (Purple)
        if (['interested', 'meeting scheduled', 'demo scheduled'].includes(s))
            return 'bg-purple-50 text-purple-700 ring-purple-600/20';

        // Follow-Up Group (Pink) - Now includes Call Later/Callback
        if (['follow-up', 'follow up', 'call later', 'callback'].includes(s))
            return 'bg-pink-50 text-pink-700 ring-pink-600/20';

        // Converted Group (Indigo)
        if (s === 'converted') return 'bg-indigo-50 text-indigo-700 ring-indigo-600/20';

        // Won Group (Green)
        if (['won', 'closed'].includes(s)) return 'bg-green-50 text-green-700 ring-green-600/20';

        // Lost Group (Red)
        if (['lost', 'junk', 'wrong number', 'invalid', 'not interested', 'not intersted'].includes(s))
            return 'bg-red-50 text-red-700 ring-red-600/10';

        return 'bg-gray-50 text-gray-600 ring-gray-500/10';
    }

    renderPagination(currentPage, totalPages) {
        // Safe defaults
        currentPage = parseInt(currentPage) || 1;
        totalPages = parseInt(totalPages) || 0;

        if (totalPages <= 1) {
            this.paginationContainer.innerHTML = '';
            return;
        }

        let buttons = '';
        if (currentPage > 1) {
            buttons += `<button onclick="leadsManager.loadLeads(${currentPage - 1})" class="px-3 py-1 border rounded hover:bg-gray-100 mr-2">Prev</button>`;
        }

        buttons += `<span class="px-3 py-1 text-gray-600">Page ${currentPage} of ${totalPages}</span>`;

        if (currentPage < totalPages) {
            buttons += `<button onclick="leadsManager.loadLeads(${currentPage + 1})" class="px-3 py-1 border rounded hover:bg-gray-100 ml-2">Next</button>`;
        }

        this.paginationContainer.innerHTML = `<div class="flex justify-center items-center">${buttons}</div>`;
    }

    /* ------------------------------
       SEARCH & DATE FILTERS
    ------------------------------ */
    initSearch() {
        // Debounce search input
        const searchInput = document.getElementById('leadSearchInput');
        if (searchInput) {
            let timeout = null;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(timeout);
                timeout = setTimeout(() => {
                    this.searchQuery = e.target.value.trim();
                    this.loadLeads(1);
                }, 500);
            });
        }
    }

    filterToday() {
        const d = new Date();
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const today = `${year}-${month}-${day}`;
        this.start_date = today;
        this.end_date = today;

        // Update UI
        document.getElementById('leadsDateFilter').value = today;

        // Highlight button (optional)
        const btn = document.getElementById('btn-leads-today');
        if (btn) btn.classList.add('bg-blue-50', 'text-blue-600', 'border-blue-300');

        this.loadLeads(1);
    }


    /* ------------------------------
       AGENT ASSIGNMENT
    ------------------------------ */
    async loadAgents() {
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/pipeline/agents');
            if (resp && resp.ok) {
                const data = await resp.json();
                this.agents = data.agents || [];
            }
        } catch (e) {
            console.error("Error loading agents:", e);
        }
    }

    renderAgentOptions(currentAgentId) {
        return this.agents.map(agent => `
            <option value="${agent.id}" ${agent.id == currentAgentId ? 'selected' : ''}>${agent.name}</option>
        `).join('');
    }

    async updateLeadAgent(leadId, agentId) {
        try {
            const resp = await auth.makeAuthenticatedRequest(`/api/leads/${leadId}/assign`, {
                method: 'PUT',
                body: JSON.stringify({ agent_id: agentId || null })
            });

            if (resp && resp.ok) {
                // Success: Dispatch update
                const event = new CustomEvent('leadAssigned', { detail: { leadId, agentId } });
                window.dispatchEvent(event);
            } else {
                alert("Failed to assign agent");
                this.loadLeads(this.currentPage || 1); // Revert
            }
        } catch (e) {
            console.error("Error signing agent:", e);
            alert("Error assigning agent");
        }
    }

    filterCustomDate(val) {
        if (!val) {
            this.start_date = null;
            this.end_date = null;
        } else {
            this.start_date = val;
            this.end_date = val; // Single day pick for now
        }

        // Reset Today button style
        const btn = document.getElementById('btn-leads-today');
        if (btn) btn.classList.remove('bg-blue-50', 'text-blue-600', 'border-blue-300');

        this.loadLeads(1);
    }

    /* ------------------------------
       HISTORY MODAL
    ------------------------------ */
    showHistory(leadId) {
        const lead = this.leads.find(l => l.id === leadId);
        if (!lead) return;

        this.histLead = lead; // Store for tab switching

        // UI Setup
        document.getElementById('leadHistoryModal').classList.remove('hidden');
        document.getElementById('histModalName').textContent = lead.name || lead.phone;

        // Load Unified Timeline
        this.loadUnifiedTimeline();
    }

    async loadUnifiedTimeline() {
        const container = document.getElementById('leadHistoryModalContent');
        container.innerHTML = '<div class="text-gray-500 text-sm p-4">Loading complete history...</div>';

        try {
            // Fetch Both in Parallel
            const [statusResp, followResp] = await Promise.all([
                auth.makeAuthenticatedRequest(`/api/leads/${this.histLead.id}/history/status`),
                auth.makeAuthenticatedRequest(`/api/admin/followups?lead_id=${this.histLead.id}`)
            ]);

            let timelineItems = [];

            const parseAsUTC = (dateStr) => {
                if (!dateStr) return new Date();
                // Ensure 'Z' is present for UTC parsing
                if (dateStr.indexOf('Z') === -1 && dateStr.indexOf('+') === -1) {
                    return new Date(dateStr + 'Z');
                }
                return new Date(dateStr);
            };

            // Process Status History
            if (statusResp && statusResp.ok) {
                const sData = await statusResp.json();
                (sData.history || []).forEach(h => {
                    timelineItems.push({
                        type: 'status',
                        date: parseAsUTC(h.created_at),
                        title: `Status Changed to ${h.new_status.toUpperCase()}`,
                        desc: `Previous: ${h.old_status || 'N/A'}`,
                        icon: 'fa-exchange-alt',
                        color: 'bg-blue-100 text-blue-600'
                    });
                });
            }

            // Process Follow-ups
            if (followResp && followResp.ok) {
                const fData = await followResp.json();
                (fData.followups || []).forEach(f => {
                    timelineItems.push({
                        type: 'followup',
                        date: parseAsUTC(f.scheduled_at),
                        title: `Follow-up: ${f.status.toUpperCase()}`, // assigned to? 
                        desc: f.notes || 'No notes',
                        icon: 'fa-calendar-check',
                        color: 'bg-green-100 text-green-600'
                    });
                });
            }

            // Sort: Newest First
            timelineItems.sort((a, b) => b.date - a.date);

            if (timelineItems.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-6 text-gray-500 text-sm">
                        <p>No history found.</p>
                        <p class="text-xs text-gray-400 mt-1">Current Status: <span class="capitalize font-bold text-blue-600">${this.histLead.status}</span></p>
                    </div>
                 `;
                return;
            }

            // Render Unified Timeline
            const html = timelineItems.map((item, index) => {
                return `
                    <div class="relative pl-8 pb-6 border-l border-gray-200 last:border-0 last:pb-0">
                        <div class="absolute -left-3 top-0 w-6 h-6 rounded-full flex items-center justify-center ${item.color} text-xs border border-white shadow-sm">
                            <i class="fas ${item.icon}"></i>
                        </div>
                        <div class="mb-1 text-sm font-bold text-gray-900">
                            ${item.title}
                        </div>
                         <div class="text-xs text-gray-400 mb-1">
                            ${item.date.toLocaleDateString()} at ${item.date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true })}
                        </div>
                        <div class="bg-gray-50 rounded p-2 text-xs text-gray-600">
                           ${item.desc}
                        </div>
                    </div>
                 `;
            }).join('');

            container.innerHTML = `<div class="p-4">${html}</div>`;

        } catch (e) {
            console.error("Unified History Error:", e);
            container.innerHTML = `<div class="text-red-500 text-sm p-4">Error loading history: ${e.message}</div>`;
        }
    }


    /* ------------------------------
       SHOW CALL HISTORY MODAL (Legacy)
    ------------------------------ */
    async showCallHistory(phone) {
        if (!phone || phone === '-') return;

        const modal = document.getElementById('modal-call-history');
        const phoneLabel = document.getElementById('call-history-phone');
        const tbody = document.getElementById('call-history-table-body');

        if (!modal || !tbody) return;

        // Open Modal & Lock Body Scroll
        modal.classList.remove('hidden-section');
        document.body.style.overflow = 'hidden';

        if (phoneLabel) phoneLabel.textContent = phone;
        tbody.innerHTML = '<tr><td colspan="4" class="text-center py-8 text-gray-400"><i class="fas fa-circle-notch fa-spin mr-2"></i>Loading logs...</td></tr>';

        try {
            const url = `/api/admin/all-call-history?search=${encodeURIComponent(phone)}&page=1&per_page=50`;
            const resp = await auth.makeAuthenticatedRequest(url);

            if (resp && resp.ok) {
                const data = await resp.json();
                const calls = data.call_history || [];

                if (calls.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="text-center py-8 text-gray-400">No call history found for this number.</td></tr>';
                    return;
                }

                tbody.innerHTML = calls.map(call => {
                    const dateObj = new Date(call.timestamp);
                    const dateStr = dateObj.toLocaleDateString() + ' ' + dateObj.toLocaleTimeString();

                    // Format Duration
                    const dur = call.duration ? `${Math.floor(call.duration / 60)}m ${call.duration % 60}s` : '0s';

                    // Call Type Badge
                    let typeBadge = `<span class="px-2 py-0.5 text-xs rounded bg-gray-100 text-gray-600">${call.call_type}</span>`;
                    const cType = (call.call_type || '').toLowerCase();

                    if (cType === 'incoming') typeBadge = `<span class="px-2 py-0.5 text-xs rounded bg-green-100 text-green-700"><i class="fas fa-arrow-down mr-1"></i>Incoming</span>`;
                    else if (cType === 'outgoing') typeBadge = `<span class="px-2 py-0.5 text-xs rounded bg-blue-100 text-blue-700"><i class="fas fa-arrow-up mr-1"></i>Outgoing</span>`;
                    else if (cType === 'missed') typeBadge = `<span class="px-2 py-0.5 text-xs rounded bg-red-100 text-red-700"><i class="fas fa-times mr-1"></i>Missed</span>`;
                    else if (cType === 'rejected') typeBadge = `<span class="px-2 py-0.5 text-xs rounded bg-red-100 text-red-700"><i class="fas fa-ban mr-1"></i>Rejected</span>`;

                    // Audio Player
                    let audioPlayer = '-';
                    if (call.recording_path) {
                        // DB stores 'uploads/recordings/...', frontend route is '/uploads/...' -> so '/'+recording_path works.
                        audioPlayer = `
                            <audio controls class="h-8 w-40" preload="none" onerror="this.style.display='none'; this.insertAdjacentHTML('afterend', '<span class=\\'text-xs text-red-400\\'>Error loading</span>')">
                                <source src="/${call.recording_path}" type="audio/mpeg">
                                <source src="/${call.recording_path}" type="audio/wav"> <!-- Fallback -->
                            </audio>
                         `;
                    }

                    return `
                        <tr class="hover:bg-gray-50">
                            <td class="px-6 py-3 whitespace-nowrap text-sm text-gray-700">${dateStr}</td>
                            <td class="px-6 py-3 whitespace-nowrap">${typeBadge}</td>
                            <td class="px-6 py-3 whitespace-nowrap text-sm text-gray-700">${dur}</td>
                            <td class="px-6 py-3 whitespace-nowrap">${audioPlayer}</td>
                        </tr>
                    `;
                }).join('');

            } else {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center py-8 text-red-500">Failed to load history</td></tr>';
            }
        } catch (e) {
            console.error(e);
            tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-red-500">Error: ${e.message}</td></tr>`;
        }
    }


}

window.leadsManager = new LeadsManager();
