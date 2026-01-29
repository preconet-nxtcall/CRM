/* js/kanban.js - SaaS Version */

class KanbanManager {
    constructor() {
        this.container = document.getElementById('kanban-container');
        // Updated Columns per user request
        this.statusKeys = ["New", "Attempted", "Connected", "Converted", "Won", "Lost"];
        this.meta = {
            "New": { color: "blue", label: "New Leads" },
            "Attempted": { color: "yellow", label: "Attempted" },
            "Connected": { color: "indigo", label: "Connected" },
            "Converted": { color: "purple", label: "Converted" },
            "Won": { color: "green", label: "Won" },
            "Lost": { color: "red", label: "Lost" }
        };
        this.allLeads = []; // Store locally for search filtering
        this.agents = [];
        this.currentLeadId = null;
    }

    async init() {
        if (this.initialized) return; // Prevent multiple inits
        this.initialized = true;

        const user = auth.getCurrentUser();
        // user-avatar might be in header, check if exists
        if (document.getElementById('user-avatar') && user) {
            document.getElementById('user-avatar').textContent = user.name ? user.name.substring(0, 2).toUpperCase() : 'AD';
        }

        // Initialize Date Filter Listener
        const dateFilter = document.getElementById('dateFilter');
        if (dateFilter) {
            dateFilter.addEventListener('change', () => this.render());
        }

        await this.load();
    }

    async load() {
        await Promise.all([this.loadAgents(), this.refresh()]);
    }

    /* ... DATA LOADING methods remain same ... */

    // ... (Skipping loadAgents/populateAgentDropdown to avoid massive diff, they are unchanged)

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
        // ... (Keep existing implementation)
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
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/pipeline/kanban');
            if (resp && resp.ok) {
                const data = await resp.json();
                this.processData(data.kanban);
                this.render();
            }
        } catch (e) {
            console.error("Kanban Error", e);
        }
    }

    processData(columns) {
        // Flatten for search and date filtering
        this.allLeads = [];
        this.columnData = columns; // Initial load structure

        // We assume backend might not group exactly by our new keys "Connected", so we rely on flattened list
        // and re-group in render based on lead.status
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

        const filterText = (document.getElementById('searchInput').value || '').toLowerCase();
        const dateVal = document.getElementById('dateFilter') ? document.getElementById('dateFilter').value : '';

        // Helper to reconstruct columns dynamically since we flattened data
        const tempColumns = {};
        this.statusKeys.forEach(k => tempColumns[k] = []);

        // Filter and Distribute
        this.allLeads.forEach(lead => {
            // Text Filter
            if (filterText) {
                const match = (lead.name && lead.name.toLowerCase().includes(filterText)) ||
                    (lead.phone && lead.phone.includes(filterText));
                if (!match) return;
            }

            // Date Filter (Created At)
            if (dateVal && lead.created_at) {
                const d = new Date(lead.created_at);
                const leadDate = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
                if (leadDate !== dateVal) return;
            }

            // Map status to column
            // Handle case-insensitive mapping & "Connected" logic
            let status = (lead.status || "New").toLowerCase();
            let dest = "New"; // Default

            if (["new", "new leads", "new lead"].includes(status)) dest = "New";
            else if (["attempted", "ringing", "no answer", "busy"].includes(status)) dest = "Attempted";
            else if (['connected', 'in conversation', 'meeting scheduled'].includes(status)) dest = "Connected";
            else if (['converted', 'interested'].includes(status)) dest = "Converted"; // Mapping "Interested" to "Converted" as per user flow? Or separate? 
            // User asked: "Attempted, connected converted".
            // Let's assume Converted is the stage.
            else if (['won', 'closed'].includes(status)) dest = "Won";
            else if (['lost', 'junk', 'invalid'].includes(status)) dest = "Lost";
            else if (['follow-up', 'callback'].includes(status)) dest = "Connected"; // Fallback: Map Follow-Up to Connected

            if (status.includes('follow')) dest = "Connected";

            if (tempColumns[dest]) tempColumns[dest].push(lead);
        });

        this.statusKeys.forEach(status => {
            let leads = tempColumns[status] || [];

            const totalRevenue = leads.reduce((sum, item) => sum + (item.revenue || 0), 0);
            grandTotal += totalRevenue;
            grandCount += leads.length;

            const col = this.createColumn(status, leads, totalRevenue);
            this.container.appendChild(col);
        });

        document.getElementById('grand-total').textContent = this.formatMoney(grandTotal);
        const countEl = document.getElementById('total-count');
        if (countEl) countEl.textContent = grandCount;
    }

    filterCards(text) {
        // Debounce simple re-render
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => this.render(), 300);
    }

    createColumn(status, leads, revenue) {
        const meta = this.meta[status] || { color: 'gray', label: status };

        // Header Layout: Title + Count ----- Revenue
        // Sub-header: Progress Bar
        const col = document.createElement('div');
        col.className = 'kanban-col flex flex-col h-full';
        col.dataset.status = status;

        // Progress Bar Color Logic
        let barColor = "bg-gray-300";
        if (status === "New") barColor = "bg-green-500";
        else if (status === "Won") barColor = "bg-green-600";
        else if (status === "Proposition") barColor = "bg-blue-500";
        else if (status === "Qualified") barColor = "bg-blue-400";
        else barColor = `bg-${meta.color}-500`;

        col.innerHTML = `
            <div class="px-2 py-2 bg-gray-50 flex-none group">
                <div class="flex justify-between items-baseline mb-1">
                    <div class="flex items-center gap-2 font-bold text-gray-700 text-[15px]">
                        <span>${status}</span>
                        <span class="text-xs font-normal text-gray-500" title="Count">(${leads.length})</span>
                        <button onclick="kanbanManager.openModal(null, '${status.toLowerCase()}')" class="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-gray-800 transition-opacity">
                            <i class="fas fa-plus text-xs"></i>
                        </button>
                    </div>
                    <div class="font-bold text-gray-800 text-sm">
                        ${this.formatMoney(revenue)}
                    </div>
                </div>
                
                <div class="h-1.5 w-full bg-gray-200 rounded-full overflow-hidden flex">
                    <div class="${barColor} h-full" style="width: ${leads.length > 0 ? '70%' : '0%'}"></div>
                </div>
            </div>
            
            <div class="kanban-cards p-2 space-y-2 overflow-y-auto flex-1 custom-scrollbar" id="col-${status}">
                 <!-- Cards -->
            </div>
        `;

        const cardContainer = col.querySelector('.kanban-cards');
        leads.forEach(lead => cardContainer.appendChild(this.createCard(lead)));

        // Sortable
        if (typeof Sortable !== 'undefined') {
            new Sortable(cardContainer, {
                group: 'kanban',
                animation: 150,
                delay: 100,
                delayOnTouchOnly: true,
                ghostClass: 'sortable-ghost',
                dragClass: 'sortable-drag',
                onEnd: (evt) => this.handleDrop(evt)
            });
        }

        return col;
    }

    createCard(lead) {
        const card = document.createElement('div');
        card.className = "card bg-white p-3 rounded shadow-sm border border-gray-200 cursor-pointer relative hover:shadow-md transition-shadow select-none";
        card.dataset.id = lead.id;
        card.dataset.revenue = lead.revenue || 0;
        card.onclick = (e) => {
            if (!e.target.closest('.quick-action')) {
                this.openModal(lead.id);
            }
        };

        // Tags
        let tagsHtml = '';
        (lead.tags || []).forEach(tag => {
            const colorClass = tag.color === 'purple' ? 'bg-purple-100 text-purple-700' :
                tag.color === 'blue' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600';
            tagsHtml += `<span class="text-[10px] font-medium px-2 py-0.5 rounded-full ${colorClass}">${tag.text}</span>`;
        });

        // Priority
        const priority = lead.priority || 0;
        let starColor = "text-gray-300";
        if (priority >= 4) starColor = "text-green-500";
        else if (priority === 3) starColor = "text-yellow-400";
        else if (priority > 0) starColor = "text-red-500";

        const priorityHtml = Array(5).fill(0).map((_, i) =>
            `<i class="fa${i < priority ? 's' : 'r'} fa-star ${i < priority ? starColor : 'text-gray-200'} text-[10px]"></i>`
        ).join('');

        const cleanPhone = (lead.phone || '').replace(/\D/g, '');
        const waUrl = `https://wa.me/${cleanPhone}?text=Hello ${encodeURIComponent(lead.name)}`;
        const agentAvatar = (lead.agent_avatar || 'NA').substring(0, 2).toUpperCase();

        card.innerHTML = `
            <!-- Title -->
            <div class="font-bold text-gray-800 text-sm mb-0.5 leading-tight text-ellipsis overflow-hidden whitespace-nowrap" title="${lead.name}">
                ${lead.name}
            </div>
            
            <!-- Phone & Email -->
            <div class="text-[11px] text-gray-500 mb-1">
                ${lead.phone || ''}
            </div>
            ${lead.email ? `<div class="text-[10px] text-gray-400 mb-1 truncate" title="${lead.email}">${lead.email}</div>` : ''}

            <!-- Revenue -->
            <div class="text-xs font-bold text-gray-900 mb-1">
                ${lead.revenue > 0 ? this.formatMoney(lead.revenue) : '<span class="text-gray-300">-</span>'}
            </div>

            <!-- Tags (Source / Property) -->
            <div class="flex flex-wrap gap-1 mb-3 min-h-[18px]">
                ${tagsHtml}
            </div>

            <!-- Footer -->
            <div class="flex justify-between items-center mt-auto border-t border-transparent">
                <!-- Left: Stars -->
                <div class="flex gap-0.5 cursor-pointer" title="Priority: ${priority}">
                    ${priorityHtml}
                </div>
                
                <!-- Middle: Activity Icons (Call/WA) -->
                <div class="flex gap-2 mx-auto">
                    ${cleanPhone ? `
                     <a href="tel:${cleanPhone}" class="quick-action text-gray-400 hover:text-green-600 transition-colors" title="Call" onclick="event.stopPropagation();">
                        <i class="fas fa-phone-alt text-sm"></i>
                     </a>
                     <a href="${waUrl}" target="_blank" class="quick-action text-gray-400 hover:text-green-600 transition-colors" title="WhatsApp" onclick="event.stopPropagation();">
                        <i class="fab fa-whatsapp text-[15px]"></i>
                     </a>
                    ` : ''}
                </div>
                
                <!-- Right: Avatar -->
                <div class="w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 border border-white shadow-sm flex items-center justify-center text-[9px] font-bold" title="${lead.agent}">
                    ${agentAvatar}
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
            return resp && resp.ok;
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
