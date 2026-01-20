class LeadsManager {
    constructor() {
        this.tableBody = document.getElementById('leadsTableBody');
        this.paginationContainer = document.getElementById('leadsPagination');
        this.itemsPerPage = 20;
        this.currentFilter = 'all'; // Default filter
    }

    async init() {
        // Called when view switches to 'sectionLeads'
        await this.loadLeads();
    }

    filterLeads(source) {
        this.currentFilter = source;
        this.updateFilterButtons();
        this.loadLeads(1); // Reset to page 1
    }


    updateFilterButtons() {
        // Reset all buttons

        const types = ['all', 'facebook', 'indiamart', 'magicbricks', '99acres', 'justdial'];
        types.forEach(type => {
            const btn = document.getElementById(`btn-filter-${type}`);
            if (btn) {
                let baseClass = "px-3 py-1.5 text-xs font-medium transition-colors ";

                // Determine rounded corners based on position
                if (type === 'all') baseClass += "rounded-l-lg ";
                else if (type === 'justdial') baseClass += "rounded-r-lg "; // changed last element
                else baseClass += ""; // Middle buttons

                if (type === this.currentFilter) {
                    btn.className = baseClass + "text-white bg-blue-600 border border-blue-600 hover:bg-blue-700";
                } else {
                    btn.className = baseClass + "text-gray-700 bg-white border-t border-b border-r border-gray-200 hover:bg-gray-100" + (type === 'all' ? " border-l" : "");
                }
            }
        });
    }

    async loadLeads(page = 1) {
        if (!this.tableBody) return;

        this.currentPage = page; // Store current page
        this.tableBody.innerHTML = '<tr><td colspan="8" class="text-center py-4">Loading...</td></tr>';

        try {
            // Include Filter in Request
            let url = `/api/facebook/leads?page=${page}&per_page=${this.itemsPerPage}`;
            if (this.currentFilter !== 'all') {
                url += `&source=${this.currentFilter}`;
            }

            const resp = await auth.makeAuthenticatedRequest(url);
            if (resp && resp.ok) {
                const data = await resp.json();
                this.leads = data.leads; // STORE LEADS LOCALLY
                this.renderTable(data.leads);
                this.renderPagination(data.current_page, data.pages);
            } else {
                let errorMsg = "Failed to load leads";
                try {
                    const errData = await resp.json();
                    if (errData.error) errorMsg = errData.error;
                } catch (e) { }
                this.tableBody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-red-500">${errorMsg}</td></tr>`;
            }
        } catch (e) {
            console.error("Error loading leads", e);
            this.tableBody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-red-500">Error: ${e.message}</td></tr>`;
        }
    }

    renderLeadDetails(lead) {
        if (!lead.custom_fields) return '-';

        if (lead.source === 'indiamart') {
            // IndiaMART Format
            const subject = lead.custom_fields.subject || 'Inquiry';
            const company = lead.custom_fields.company || '';
            const message = lead.custom_fields.message || '';

            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${subject}">${subject}</div>
                <div class="text-blue-600 font-medium truncate max-w-[200px]" title="${company}">${company}</div>
                ${message ? `<div class="text-[10px] text-gray-400 mt-1 truncate max-w-[200px]" title="${message}">${message}</div>` : ''}
            `;
        } else if (lead.source === 'call_history') {
            // Call History Format
            return `<div class="text-gray-500 italic">Manual Entry</div>`;

        } else if (lead.source === 'magicbricks') {
            // Magicbricks Format
            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${lead.property_type}">${lead.property_type || '-'}</div>
                <div class="text-gray-500 truncate max-w-[200px]" title="${lead.budget} | ${lead.location}">${lead.budget || '-'}</div>
            `;
        } else if (lead.source === '99acres') {
            // 99acres Format

            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${lead.property_type}">${lead.property_type || '-'}</div>
                <div class="text-gray-500 truncate max-w-[200px]" title="${lead.location}">${lead.location || '-'}</div>
            `;
        } else if (lead.source === 'justdial') {
            // JustDial Format
            return `
                <div class="font-bold text-gray-900 truncate max-w-[200px]" title="${lead.requirement}">${lead.requirement || 'Business Enquiry'}</div>
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

        if (lead.source === 'indiamart') {
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
        } else if (lead.source === 'magicbricks') {
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
        } else if (lead.source === '99acres') {
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
        } else if (lead.source === 'justdial') {
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
        } else {
            // Generic Fallback
            detailsHtml = `
                <div class="text-sm">
                    <pre class="bg-gray-50 p-3 rounded overflow-x-auto text-xs text-gray-700">${JSON.stringify(lead, null, 2)}</pre>
                </div>
             `;
        }

        content.innerHTML = detailsHtml;
        modal.classList.remove('hidden');
    }

    renderTable(leads) {
        if (!leads || leads.length === 0) {
            this.tableBody.innerHTML = `<tr><td colspan="9" class="text-center py-8 text-gray-500">No leads found.</td></tr>`;
            return;
        }

        this.tableBody.innerHTML = leads.map(lead => {
            // Enhanced Date Formatting (Local Time, Cleaner)
            let dateStr = lead.created_at;
            if (!dateStr.endsWith('Z')) {
                dateStr += 'Z'; // Treat as UTC
            }
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
            if (lead.status === 'new') statusColor = "bg-green-100 text-green-800";
            if (lead.status === 'contacted') statusColor = "bg-blue-100 text-blue-800";
            if (lead.status === 'qualified') statusColor = "bg-purple-100 text-purple-800";
            if (lead.status === 'converted') statusColor = "bg-yellow-100 text-yellow-800";
            if (lead.status === 'junk') statusColor = "bg-red-100 text-red-800";

            let sourceBadge = `<span class="px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-800 rounded">${lead.source.toUpperCase()}</span>`;
            if (lead.source === 'facebook') sourceBadge = `<span class="px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-800 rounded">FACEBOOK</span>`;

            if (lead.source === 'indiamart') sourceBadge = `<span class="px-2 py-0.5 text-xs font-medium bg-indigo-100 text-indigo-800 rounded">INDIAMART</span>`;
            if (lead.source === 'magicbricks') sourceBadge = `<span class="px-2 py-0.5 text-xs font-medium bg-red-100 text-red-800 rounded">MAGICBRICKS</span>`;
            if (lead.source === '99acres') sourceBadge = `<span class="px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-800 rounded">99ACRES</span>`;

            return `
                <tr class="hover:bg-gray-50 transition-colors">
                    <td class="px-4 py-3 whitespace-nowrap text-xs">${dateHtml}</td>
                    <td class="px-4 py-3 font-medium text-gray-900 whitespace-nowrap">${lead.name || '-'}</td>
                    <td class="px-4 py-3 text-blue-600 whitespace-nowrap custom-copy-text cursor-pointer" onclick="navigator.clipboard.writeText('${lead.phone}')" title="Click to copy">${lead.phone || '-'}</td>
                    <td class="px-4 py-3 text-gray-500 whitespace-nowrap">${lead.email || '-'}</td>
                    <td class="px-4 py-3">${sourceBadge}</td>
                    <td class="px-4 py-3 leading-tight">${this.renderLeadDetails(lead)}</td>
                    <td class="px-4 py-3 text-gray-600">${lead.assigned_agent_name || 'Unassigned'}</td>
                    <td class="px-4 py-3">
                         <select onchange="leadsManager.updateLeadStatus(${lead.id}, this.value)" 
                            class="text-xs rounded border-gray-200 shadow-sm focus:border-blue-500 focus:ring focus:ring-blue-200 focus:ring-opacity-50 ${statusColor}">
                            <option value="new" ${lead.status === 'new' ? 'selected' : ''}>New</option>
                            <option value="contacted" ${lead.status === 'contacted' ? 'selected' : ''}>Contacted</option>
                            <option value="qualified" ${lead.status === 'qualified' ? 'selected' : ''}>Qualified</option>
                            <option value="converted" ${lead.status === 'converted' ? 'selected' : ''}>Converted</option>
                            <option value="junk" ${lead.status === 'junk' ? 'selected' : ''}>Junk</option>
                        </select>
                    </td>
                    <td class="px-4 py-3 text-right">
                        <button onclick="leadsManager.openLeadModal(${lead.id})" 
                                class="text-gray-500 hover:text-blue-600 transition-colors p-2 rounded-full hover:bg-blue-50"
                                title="View Details">
                            <i class="fas fa-eye"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    renderStatusOptions(currentStatus) {
        const statuses = ['new', 'contacted', 'converted', 'junk'];
        return statuses.map(s => `
            <option value="${s}" ${s === currentStatus ? 'selected' : ''}>${s.charAt(0).toUpperCase() + s.slice(1)}</option>
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
        switch (status) {
            case 'new': return 'bg-green-50 text-green-700 ring-green-600/20';
            case 'contacted': return 'bg-yellow-50 text-yellow-800 ring-yellow-600/20';
            case 'converted': return 'bg-blue-50 text-blue-700 ring-blue-700/10';
            case 'junk': return 'bg-red-50 text-red-700 ring-red-600/10';
            default: return 'bg-gray-50 text-gray-600 ring-gray-500/10';
        }
    }

    renderPagination(currentPage, totalPages) {
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
}

window.leadsManager = new LeadsManager();
