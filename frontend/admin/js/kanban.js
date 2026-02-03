/* js/kanban.js - SaaS Version */

class KanbanManager {
    constructor() {
        this.container = document.getElementById('kanban-container');
        // Updated Columns per Enterprise UI specs
        this.statusKeys = ["New", "Attempted", "Converted", "Won"];
        this.meta = {
            "New": { color: "blue", label: "Awareness" },
            "Attempted": { color: "yellow", label: "Attempted" },
            "Converted": { color: "purple", label: "Converted" },
            "Won": { color: "green", label: "Purchase" }
        };
        this.allLeads = [];
        this.agents = [];
        this.currentLeadId = null;
        this.PAGE_SIZE = 20;
        this.visibleCounts = {};
    }

    async init() {
        if (this.initialized) return;
        this.initialized = true;

        const user = auth.getCurrentUser();
        if (document.getElementById('user-avatar') && user) {
            document.getElementById('user-avatar').textContent = user.name ? user.name.substring(0, 2).toUpperCase() : 'AD';
        }

        const dateFilter = document.getElementById('dateFilter');
        if (dateFilter) {
            dateFilter.addEventListener('change', () => this.render());
        }

        window.addEventListener('leadStatusUpdated', () => {
            console.log("Kanban: Syncing external update...");
            this.refresh();
        });

        // Add custom styles for scrollbar and exact gaps if not in CSS
        const style = document.createElement('style');
        style.innerHTML = `
            #kanban-container {
                display: flex;
                gap: 10px; /* Reduced to 10px */
                overflow-x: auto;
                padding-bottom: 20px;
                background-color: #F8FAFC; /* Very light gray */
                align-items: flex-start;
                height: 100%;
            }
            .kanban-col {
                min-width: 320px;
                width: 320px;
                flex-shrink: 0;
            }
            .custom-scrollbar::-webkit-scrollbar {
                width: 6px;
            }
            .custom-scrollbar::-webkit-scrollbar-thumb {
                background-color: #CBD5E1;
                border-radius: 4px;
            }
        `;
        document.head.appendChild(style);

        await this.load();
    }

    /* ... DATA LOADING methods remain same ... */
    // Kept load, loadAgents, populateAgentDropdown, refresh, updateStatus... 
    // We only replace the UI rendering parts mainly.

    async load() { // kept shorter for replace match if needed, but including full init above
        await Promise.all([this.loadAgents(), this.refresh()]);
    }

    // ... (Keeping loadAgents, populateAgentDropdown as they were in original file if possible, or re-declaring them to be safe) ...
    // To ensure I don't delete them, I will include standard implementations for this block or use the previous context.
    // Since I'm replacing a huge chunk, I should probably provide the full class implementation or be careful with start/end lines.
    // The user tool `replace_file_content` replaces a contiguous block. 
    // I will replace from `constructor` down to `createCard` end to ensure clean state.

    async loadAgents() {
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/pipeline/agents');
            if (resp && resp.ok) {
                const data = await resp.json();
                this.agents = data.agents || [];
                this.populateAgentDropdown();
            }
        } catch (e) { console.warn("Agents load warning", e); }
    }

    populateAgentDropdown() {
        const sel = document.getElementById('leadAgent');
        if (!sel) return;
        sel.innerHTML = '<option value="">-- Unassigned --</option>';
        this.agents.forEach(a => {
            sel.innerHTML += `<option value="${a.id || a.user_id || ''}">${a.name}</option>`;
        });
        if (this.agents.length === 0) {
            auth.makeAuthenticatedRequest('/api/admin/users?per_page=100').then(r => r.json()).then(d => {
                (d.users || []).forEach(u => {
                    sel.innerHTML += `<option value="${u.id}">${u.name}</option>`;
                });
            }).catch(() => { });
        }
    }

    async refresh() {
        this.showLoading(); // Show Skeleton
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/pipeline/kanban');
            if (resp && resp.ok) {
                const data = await resp.json();
                this.processData(data.kanban);
                this.render();
            } else {
                throw new Error("API Error: " + (resp ? resp.status : "Unknown"));
            }
        } catch (e) {
            console.error("Kanban Error", e);
            this.container.innerHTML = `<div class="p-8 text-center text-red-500">
                <i class="fas fa-exclamation-triangle mb-2 text-2xl"></i><br>
                Failed to load board. <button onclick="kanbanManager.refresh()" class="underline font-bold text-blue-600 hover:text-blue-800">Retry</button>
            </div>`;
            document.getElementById('grand-total').textContent = 'Error';
        }
    }

    showLoading() {
        // Skeleton Column
        const cardSkeleton = `
            <div class="bg-white p-3 rounded-xl border border-gray-100 mb-3 animate-pulse">
                <div class="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
                <div class="h-3 bg-gray-100 rounded w-1/2 mb-3"></div>
                <div class="flex gap-2 mb-3">
                    <div class="h-5 w-12 bg-gray-100 rounded-full"></div>
                    <div class="h-5 w-16 bg-gray-100 rounded-full"></div>
                </div>
                <div class="border-t border-gray-50 pt-2 flex justify-between">
                    <div class="flex gap-1">
                         <div class="w-3 h-3 bg-gray-200 rounded-full"></div>
                         <div class="w-3 h-3 bg-gray-200 rounded-full"></div>
                    </div>
                    <div class="w-6 h-6 bg-gray-200 rounded-full"></div>
                </div>
            </div>
        `;

        // Generate Columns
        let html = '';
        this.statusKeys.forEach(status => {
            const meta = this.meta[status];
            html += `
                <div class="kanban-col flex flex-col h-full" style="min-width: 320px;">
                    <div class="mb-4 animate-pulse">
                        <div class="flex justify-between items-center mb-2 px-1">
                             <div class="h-5 bg-gray-200 rounded w-1/3"></div>
                             <div class="h-4 bg-gray-200 rounded w-1/4"></div>
                        </div>
                        <div class="h-1.5 w-full bg-gray-200 rounded-full overflow-hidden">
                             <div class="bg-gray-300 h-full rounded-full" style="width: 40%"></div>
                        </div>
                    </div>
                    <div class="space-y-2 overflow-y-hidden pr-1">
                        ${cardSkeleton.repeat(3)}
                    </div>
                </div>
            `;
        });

        this.container.innerHTML = html;
        document.getElementById('grand-total').textContent = '...';
    }

    processData(columns) {
        this.allLeads = [];
        this.columnData = columns;
        Object.keys(columns).forEach(status => {
            columns[status].forEach(lead => {
                this.allLeads.push(lead);
            });
        });
    }

    render() {
        this.container.innerHTML = '';
        let grandTotal = 0;
        let grandCount = 0;

        // Group leads by status
        const tempColumns = {};
        this.statusKeys.forEach(k => tempColumns[k] = []);

        const leads = this.getFilteredLeads();

        leads.forEach(lead => {
            const dest = this.mapStatusToColumn(lead.status);
            if (dest && tempColumns[dest]) {
                tempColumns[dest].push(lead);
            }
        });

        this.statusKeys.forEach(status => {
            let colLeads = tempColumns[status] || [];
            const totalRevenue = colLeads.reduce((sum, item) => sum + (item.revenue || 0), 0);
            grandTotal += totalRevenue;
            grandCount += colLeads.length;

            const col = this.createColumn(status, colLeads, totalRevenue);
            this.container.appendChild(col);
        });

        document.getElementById('grand-total').textContent = this.formatMoney(grandTotal);
    }

    // Helper to centralize filtering logic
    getFilteredLeads() {
        const filterText = (document.getElementById('searchInput').value || '').toLowerCase();
        const dateVal = document.getElementById('dateFilter') ? document.getElementById('dateFilter').value : '';

        return this.allLeads.filter(lead => {
            // Text Filter
            if (filterText) {
                const match = (lead.name && lead.name.toLowerCase().includes(filterText)) ||
                    (lead.phone && lead.phone.includes(filterText));
                if (!match) return false;
            }

            // Date Filter
            if (dateVal && lead.created_at) {
                const d = new Date(lead.created_at);
                const leadDate = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
                if (leadDate !== dateVal) return false;
            }
            return true;
        });
    }

    mapStatusToColumn(rawStatus) {
        let status = (rawStatus || "New").toLowerCase();

        if (["new", "new leads", "new lead"].includes(status)) return "New";

        if (['attempted', 'ringing', 'no answer', 'busy', 'not reachable', 'switch off',
            'connected', 'contacted', 'in conversation', 'meeting scheduled',
            'follow-up', 'follow up', 'call later', 'callback'].includes(status)) {
            return "Attempted";
        }

        if (['converted', 'interested', 'proposition', 'qualified', 'demo scheduled'].includes(status)) return "Converted";

        if (['won', 'closed'].includes(status)) return "Won";

        // Lost/Junk -> Ignore or handle? User said ignore "Lost".
        return null;
    }

    filterCards(text) {
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => this.render(), 300);
    }

    loadMore(status) {
        if (!this.visibleCounts[status]) this.visibleCounts[status] = this.PAGE_SIZE;
        const oldLimit = this.visibleCounts[status];
        this.visibleCounts[status] += this.PAGE_SIZE;
        const newLimit = this.visibleCounts[status];

        // Get leads for this column
        const allFiltered = this.getFilteredLeads();
        const colLeads = allFiltered.filter(l => this.mapStatusToColumn(l.status) === status);

        // Get slice to append
        const leadsToAppend = colLeads.slice(oldLimit, newLimit);
        const colContainer = document.getElementById(`col-${status}`);

        if (!colContainer) return; // Should not happen

        // Append Cards
        leadsToAppend.forEach(lead => {
            colContainer.appendChild(this.createCard(lead));
        });

        // Update "Load More" Button state
        // Find existing button div
        // Update "Load More" Button state
        // Find existing button div
        const oldBtn = colContainer.querySelector('.load-more-btn-container');
        if (oldBtn) oldBtn.remove();

        const hasMore = colLeads.length > newLimit;
        if (hasMore) {
            const remaining = colLeads.length - newLimit;
            const btnDiv = document.createElement('div');
            btnDiv.className = 'text-center pt-2 load-more-btn-container';
            btnDiv.innerHTML = `
                <button onclick="kanbanManager.loadMore('${status}')" 
                    class="text-xs font-medium text-gray-500 hover:text-gray-800 underline transition-colors">
                    Load ${remaining} more...
                </button>
            `;
            colContainer.appendChild(btnDiv);
        }
    }

    createColumn(status, leads, revenue) {
        const meta = this.meta[status] || { color: 'gray', label: status };

        const totalLeads = leads.length;
        const visibleLimit = this.visibleCounts[status] || this.PAGE_SIZE;
        const visibleLeads = leads.slice(0, visibleLimit);
        const hasMore = totalLeads > visibleLimit;

        const col = document.createElement('div');
        col.className = 'kanban-col flex flex-col h-full';
        col.dataset.status = status;

        // Progress Bar Color Logic - Fixed to use meta config
        const barColor = `bg-${meta.color}-500`;

        col.innerHTML = `
            <div class="mb-4">
                <div class="flex justify-between items-center mb-2 px-1">
                    <div class="flex items-center gap-2">
                        <span class="font-bold text-gray-800 text-[15px]">${meta.label}</span>
                        <span class="text-xs font-semibold text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">${totalLeads}</span>
                    </div>
                    <div class="text-sm font-bold text-gray-900 tracking-tight">
                        ${this.formatMoney(revenue)}
                    </div>
                </div>
                
                <!-- Thin Progress Bar -->
                <div class="h-1.5 w-full bg-gray-200 rounded-full overflow-hidden">
                    <div class="${barColor} h-full rounded-full" style="width: 100%"></div>
                </div>
            </div>
            
            <div class="kanban-cards space-y-2 overflow-y-auto flex-1 custom-scrollbar pb-4 pr-1" id="col-${status}">
                 <!-- Cards injected here -->
            </div>
        `;

        const cardContainer = col.querySelector('.kanban-cards');
        visibleLeads.forEach(lead => cardContainer.appendChild(this.createCard(lead)));

        if (hasMore) {
            const remaining = totalLeads - visibleLimit;
            const btnDiv = document.createElement('div');
            btnDiv.className = 'text-center pt-2 load-more-btn-container';
            btnDiv.innerHTML = `
                <button onclick="kanbanManager.loadMore('${status}')" 
                    class="text-xs font-medium text-gray-500 hover:text-gray-800 underline transition-colors">
                    Load ${remaining} more...
                </button>
            `;
            cardContainer.appendChild(btnDiv);
        }

        if (typeof Sortable !== 'undefined') {
            new Sortable(cardContainer, {
                group: 'kanban',
                animation: 150,
                delay: 100,
                delayOnTouchOnly: true,
                ghostClass: 'opacity-50',
                dragClass: 'scale-105',
                onEnd: (evt) => this.handleDrop(evt)
            });
        }

        return col;
    }

    createCard(lead) {
        const card = document.createElement('div');
        // Compact Enterprise Style: White, Rounded 12px, Shadow, Border Light, Padding 12px (p-3)
        card.className = "card bg-white p-3 rounded-xl shadow-sm border border-gray-100 cursor-pointer relative hover:shadow-md transition-all select-none group";
        card.dataset.id = lead.id;
        card.dataset.revenue = lead.revenue || 0;
        card.onclick = (e) => {
            if (!e.target.closest('.quick-action')) {
                this.openModal(lead.id);
            }
        };

        // Tags Pill Style
        let tagsHtml = '';
        (lead.tags || []).forEach(tag => {
            const colorClass = tag.color === 'purple' ? 'bg-purple-100 text-purple-700' :
                tag.color === 'blue' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600';
            tagsHtml += `<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full ${colorClass}">${tag.text}</span>`;
        });

        // 5-Star Rating
        const priority = lead.priority || 0;
        const priorityHtml = Array(5).fill(0).map((_, i) =>
            `<i class="fa${i < priority ? 's' : 'r'} fa-star ${i < priority ? 'text-yellow-400' : 'text-gray-200'} text-xs"></i>`
        ).join('');

        const cleanPhone = (lead.phone || '').replace(/\D/g, '');
        const waUrl = `https://wa.me/${cleanPhone}?text=Hello ${encodeURIComponent(lead.name)}`;
        const agentInitials = (lead.agent || 'NA').substring(0, 2).toUpperCase();

        // SVG Icons
        const iconWa = `<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>`;
        const iconMail = `<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>`;

        card.innerHTML = `
            <!-- Header: Name & Price -->
            <div class="flex justify-between items-start mb-0.5">
                <div class="font-bold text-gray-900 text-sm leading-tight truncate pr-2 w-full" title="${lead.name}">
                    ${lead.name}
                </div>
                <div class="font-bold text-gray-900 text-sm whitespace-nowrap">
                    ${lead.revenue > 0 ? this.formatMoney(lead.revenue) : ''}
                </div>
            </div>

            <!-- Details: Phone & Email -->
            <div class="mb-2">
                <div class="text-[11px] text-gray-500 mb-0.5 truncate">${lead.phone || ''}</div>
                ${lead.email ? `<div class="text-[10px] text-gray-400 truncate">${lead.email}</div>` : ''}
            </div>

            <!-- Tags -->
            <div class="flex flex-wrap gap-1.5 mb-2 min-h-[20px]">
                ${tagsHtml}
            </div>

            <!-- Footer Action Row -->
            <div class="flex items-center justify-between mt-auto pt-1.5 border-t border-gray-50 relative">
                <!-- Left: Stars -->
                <div class="flex gap-0.5" title="Priority: ${priority}">
                    ${priorityHtml}
                </div>

                <!-- Action Buttons: Center Aligned - Adjusted Position -->
                <div class="flex items-center gap-2 absolute left-1/2 transform -translate-x-1/2 top-1.5">
                     ${cleanPhone ? `
                     <a href="${waUrl}" target="_blank" class="quick-action transition-transform hover:scale-110" title="WhatsApp" onclick="event.stopPropagation();">
                        <div class="w-7 h-7 flex items-center justify-center rounded-full shadow-sm" style="background-color: #25D366;">
                            ${iconWa}
                        </div>
                     </a>` : ''}
                    
                    ${lead.email ? `
                     <a href="mailto:${lead.email}" class="quick-action transition-transform hover:scale-110" title="Email" onclick="event.stopPropagation();">
                        <div class="w-7 h-7 flex items-center justify-center rounded-full shadow-sm" style="background-color: #EF4444;">
                            ${iconMail}
                        </div>
                     </a>` : ''}
                </div>

                <!-- User Badge -->
                <div class="w-6 h-6 rounded-full bg-blue-100 text-blue-600 border-2 border-white shadow-sm flex items-center justify-center text-[9px] font-bold" title="Assigned to ${lead.agent}">
                    ${agentInitials}
                </div>
            </div>
        `;
        return card;
    }

    /* ------------------------------------------------
       INTERACTIONS
    ------------------------------------------------ */
    handleDrop(evt) {
        const item = evt.item;
        const newStatus = evt.to.closest('.kanban-col').dataset.status;
        const oldStatus = evt.from.closest('.kanban-col').dataset.status;
        const id = item.dataset.id;

        if (newStatus === oldStatus) return;

        // Optimistically updated UI
        this.updateStatus(id, newStatus).then(ok => {
            if (!ok) {
                evt.from.appendChild(item); // Revert
                auth.showNotification("Failed to move deal", "error");
            } else {
                // CRITICAL: Update local model to prevent reversion on filter/search
                const localLead = this.allLeads.find(l => l.id == id);
                if (localLead) {
                    localLead.status = newStatus;
                }

                this.updateTotalsUI();
                auth.showNotification(`Moved to ${newStatus}`, "success");
            }
        });
    }

    updateTotalsUI() {
        let grandTotal = 0;
        let grandCount = 0;

        document.querySelectorAll('.kanban-col').forEach(col => {
            const cards = col.querySelectorAll('.card');
            let colRevenue = 0;

            cards.forEach(card => {
                colRevenue += parseFloat(card.dataset.revenue || 0);
                grandCount++;
            });

            grandTotal += colRevenue;

            // Update Column Header Count
            const countBadge = col.querySelector('[title="Count"]');
            if (countBadge) countBadge.textContent = `(${cards.length})`;

            // Update Column Revenue
            const headerRevenue = col.querySelector('.px-2.py-2 .font-bold.text-gray-800.text-sm');
            if (headerRevenue) headerRevenue.textContent = this.formatMoney(colRevenue);
        });

        const totalEl = document.getElementById('grand-total');
        if (totalEl) totalEl.textContent = this.formatMoney(grandTotal);

        const countEl = document.getElementById('total-count');
        if (countEl) countEl.textContent = grandCount;
    }

    async updateStatus(id, status) {
        try {
            const resp = await auth.makeAuthenticatedRequest(`/api/pipeline/update_status/${id}`, {
                method: 'POST',
                body: JSON.stringify({ status })
            });

            if (resp && resp.ok) {
                // Dispatch specific event for other components
                window.dispatchEvent(new CustomEvent('leadStatusUpdated', {
                    detail: { leadId: id, newStatus: status }
                }));
                return true;
            }
            return false;
        } catch (e) { return false; }
    }

    /* ------------------------------------------------
       MODAL LOGIC
    ------------------------------------------------ */
    setRating(val) {
        document.getElementById('leadPriority').value = val;
        const container = document.getElementById('star-rating-input');
        const stars = container.querySelectorAll('i');

        let activeColor = "text-yellow-400"; // Default fallback
        if (val >= 4) activeColor = "text-green-500";
        else if (val === 3) activeColor = "text-yellow-400";
        else if (val > 0) activeColor = "text-red-500";

        stars.forEach((star, index) => {
            const starValue = index + 1;

            // Reset base classes
            star.className = "text-lg cursor-pointer hover:scale-110 transition-transform fa-star";

            if (starValue <= val) {
                star.classList.add('fas'); // Solid
                star.classList.add(activeColor);
            } else {
                star.classList.add('far'); // Outline
                star.classList.add('text-gray-300');
            }
        });
    }

    openModal(id = null, status = 'new') {
        this.currentLeadId = id;
        const modal = document.getElementById('leadModal');
        const title = document.getElementById('modalTitle');
        const btnDelete = document.getElementById('btnDelete');

        // Reset Form
        document.getElementById('leadForm').reset();
        this.setRating(0); // Reset stars

        if (id) {
            title.textContent = "Edit Deal";
            btnDelete.classList.remove('hidden');

            // Find data
            const lead = this.allLeads.find(l => l.id == id);
            if (lead) {
                document.getElementById('leadName').value = lead.name || '';
                document.getElementById('leadPhone').value = lead.phone || '';
                document.getElementById('leadEmail').value = lead.email || '';
                // Use numeric revenue/budget preference, fallback to display or 0
                document.getElementById('leadBudget').value = (lead.budget !== undefined ? lead.budget : lead.revenue) || '';
                document.getElementById('leadStatus').value = (lead.status || 'new').toLowerCase();
                document.getElementById('leadProperty').value = lead.property_type || '';
                document.getElementById('leadLocation').value = lead.location || '';
                document.getElementById('leadNotes').value = lead.requirement || '';
                document.getElementById('leadAgent').value = lead.assigned_to || ''; // Try to map ID if available

                // Priority
                this.setRating(lead.priority || 0);
            }
        } else {
            title.textContent = "New Deal";
            btnDelete.classList.add('hidden');
            document.getElementById('leadStatus').value = status.toLowerCase();
        }

        modal.classList.add('open');
    }

    // Helper to get full details for modal
    async fetchFullLeadDetails(id) {
        // We reuse the list logic or create a generic /api/admin/leads/ID if exists.
        // Or just use what we have. The user can overwrite.
        // Actually, let's leave it as is. If fields are empty, they are empty.
    }

    closeModal() {
        document.getElementById('leadModal').classList.remove('open');
        this.currentLeadId = null;
    }

    async saveLead() {
        const id = this.currentLeadId;
        // Sanitize budget input to ensure numeric value
        const rawBudget = document.getElementById('leadBudget').value;
        const sanitizedBudget = rawBudget ? rawBudget.replace(/[^0-9.]/g, '') : '0';

        const payload = {
            name: document.getElementById('leadName').value,
            phone: document.getElementById('leadPhone').value,
            email: document.getElementById('leadEmail').value,
            budget: sanitizedBudget,
            status: document.getElementById('leadStatus').value,
            property_type: document.getElementById('leadProperty').value,
            location: document.getElementById('leadLocation').value,
            requirement: document.getElementById('leadNotes').value,
            assigned_to: document.getElementById('leadAgent').value,
            priority: document.getElementById('leadPriority').value
        };

        try {
            let url = '/api/pipeline/leads';
            let method = 'POST';

            if (id) {
                url = `/api/pipeline/leads/${id}`; // PUT router
                method = 'PUT';
            }

            const resp = await auth.makeAuthenticatedRequest(url, {
                method: method,
                body: JSON.stringify(payload)
            });

            if (resp && resp.ok) {
                this.closeModal();
                this.refresh(); // Reload board
                auth.showNotification(id ? "Deal updated" : "Deal created", "success");
            } else {
                auth.showNotification("Save failed", "error");
            }
        } catch (e) {
            console.error(e);
            auth.showNotification("Error saving deal", "error");
        }
    }

    async deleteLead() {
        if (!confirm("Are you sure you want to delete this deal? This cannot be undone.")) return;

        try {
            const resp = await auth.makeAuthenticatedRequest(`/api/pipeline/leads/${this.currentLeadId}`, {
                method: 'DELETE'
            });
            if (resp && resp.ok) {
                this.closeModal();
                this.refresh();
                auth.showNotification("Deal deleted", "success");
            }
        } catch (e) {
            auth.showNotification("Delete failed", "error");
        }
    }

    /* ------------------------------------------------
       UTILS
    ------------------------------------------------ */
    formatMoney(amount) {
        if (!amount && amount !== 0) return '';
        if (isNaN(amount)) return '';
        return '₹ ' + Math.floor(amount).toLocaleString('en-IN');
    }

    getAvatarColor(name) {
        const colors = ['bg-red-500', 'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-purple-500', 'bg-pink-500'];
        let hash = 0;
        if (!name) return colors[0];
        for (let i = 0; i < name.length; i++) {
            hash = name.charCodeAt(i) + ((hash << 5) - hash);
        }
        return colors[Math.abs(hash) % colors.length];
    }
}

window.kanbanManager = new KanbanManager();
document.addEventListener('DOMContentLoaded', () => {
    kanbanManager.init();
});
