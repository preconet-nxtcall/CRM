class LeadsManager {
    constructor() {
        this.tableBody = document.getElementById('leadsTableBody');
        this.paginationContainer = document.getElementById('leadsPagination');
        this.itemsPerPage = 20;
    }

    async init() {
        // Called when view switches to 'sectionLeads'
        await this.loadLeads();
    }

    async loadLeads(page = 1) {
        if (!this.tableBody) return;

        this.tableBody.innerHTML = '<tr><td colspan="8" class="text-center py-4">Loading...</td></tr>';

        try {
            const resp = await auth.makeAuthenticatedRequest(`/api/facebook/leads?page=${page}&per_page=${this.itemsPerPage}`);
            if (resp && resp.ok) {
                const data = await resp.json();
                this.renderTable(data.leads);
                this.renderPagination(data.current_page, data.pages);
            } else {
                let errorMsg = "Failed to load leads";
                try {
                    const errData = await resp.json();
                    if (errData.error) errorMsg = errData.error;
                } catch (e) { }
                this.tableBody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-red-500">${errorMsg}</td></tr>`;
            }
        } catch (e) {
            console.error("Error loading leads", e);
            this.tableBody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-red-500">Error: ${e.message}</td></tr>`;
        }
    }

    renderTable(leads) {
        if (!leads || leads.length === 0) {
            this.tableBody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-gray-500">No leads found yet.</td></tr>';
            return;
        }

        this.tableBody.innerHTML = leads.map(lead => `
            <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-4 py-3 whitespace-nowrap text-gray-600">${new Date(lead.created_at).toLocaleString()}</td>
                <td class="px-4 py-3 font-medium text-gray-900">${lead.name || '-'}</td>
                <td class="px-4 py-3 text-blue-600">${lead.phone || '-'}</td>
                <td class="px-4 py-3 text-gray-500">${lead.email || '-'}</td>
                <td class="px-4 py-3"><span class="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs uppercase font-bold">${lead.source}</span></td>
                <td class="px-4 py-3 text-gray-500 text-xs">
                    ${lead.custom_fields && lead.custom_fields.campaign_name ? `<div class="font-bold">${lead.custom_fields.campaign_name}</div>` : ''}
                    ${lead.custom_fields && lead.custom_fields.ad_name ? `<div>${lead.custom_fields.ad_name}</div>` : ''}
                    ${!lead.custom_fields || (!lead.custom_fields.campaign_name && !lead.custom_fields.ad_name) ? '-' : ''}
                </td>
                <td class="px-4 py-3 text-gray-700">${lead.assigned_agent_name}</td>
                <td class="px-4 py-3">
                     <select onchange="leadsManager.updateLeadStatus(${lead.id}, this.value)" 
                             class="px-2 py-1 text-xs rounded-full capitalize cursor-pointer border-0 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6 ${this.getStatusColor(lead.status)}">
                        ${this.renderStatusOptions(lead.status)}
                     </select>
                </td>
            </tr>
        `).join('');
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
