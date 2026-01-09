class AppPerformanceManager {
    constructor() {
        this.tableBody = document.getElementById("appPerformanceTableBody");
        this.emptyState = document.getElementById("appPerformanceEmpty");
        this.userFilter = document.getElementById("appPerfUserFilter");
        this.dateInput = document.getElementById("appPerfDateFilter");
        this.currentFilter = "today";

        this.initListeners();
    }

    init() {
        if (!this.usersLoaded) {
            this.loadUsers();
            this.usersLoaded = true;
        }
        this.load();
    }

    initListeners() {
        // Date Filters
        const btnToday = document.getElementById("app-perf-filter-today");
        const btnYesterday = document.getElementById("app-perf-filter-yesterday");

        if (btnToday) {
            btnToday.addEventListener("click", () => {
                this.setFilter("today", btnToday, btnYesterday);
            });
        }

        if (btnYesterday) {
            btnYesterday.addEventListener("click", () => {
                this.setFilter("yesterday", btnYesterday, btnToday);
            });
        }

        // Date Picker
        if (this.dateInput) {
            this.dateInput.addEventListener("change", () => {
                // When picking a date, clear preset buttons
                if (btnToday) {
                    btnToday.classList.remove("bg-gray-100", "active");
                    btnToday.classList.add("hover:bg-gray-50");
                }
                if (btnYesterday) {
                    btnYesterday.classList.remove("bg-gray-100", "active");
                    btnYesterday.classList.add("hover:bg-gray-50");
                }

                this.currentFilter = "custom";
                this.load();
            });
        }

        // User Filter
        if (this.userFilter) {
            this.userFilter.addEventListener("change", () => {
                this.load();
            });
        }
    }

    setFilter(filter, activeBtn, inactiveBtn) {
        this.currentFilter = filter;

        // Clear date input when using presets
        if (this.dateInput) this.dateInput.value = "";

        activeBtn.classList.remove("hover:bg-gray-50");
        activeBtn.classList.add("bg-gray-100", "active");

        inactiveBtn.classList.remove("bg-gray-100", "active");
        inactiveBtn.classList.add("hover:bg-gray-50");

        this.load();
    }

    async loadUsers() {
        try {
            // Fix: User manual request to handle JSON parsing
            const resp = await auth.makeAuthenticatedRequest("/api/admin/users");
            if (!resp || !resp.ok) return;

            const data = await resp.json();
            const users = data.users || []; // Extract from 'users' key

            if (this.userFilter) {
                // Keep "All Users"
                this.userFilter.innerHTML = '<option value="all">All Users</option>';
                users.forEach(u => {
                    const opt = document.createElement("option");
                    opt.value = u.id;
                    opt.textContent = u.name;
                    this.userFilter.appendChild(opt);
                });
            }
        } catch (e) {
            console.error("Failed to load users for app performance", e);
        }
    }

    async load() {
        if (!this.tableBody) return;

        this.tableBody.innerHTML = '<tr><td colspan="5" class="px-6 py-4 text-center text-gray-500">Loading...</td></tr>';
        this.emptyState.classList.add("hidden");
        this.tableBody.parentElement.classList.remove("hidden");

        try {
            const userId = this.userFilter ? this.userFilter.value : "all";
            let url = `/api/admin/app_usage_records?user_id=${userId}&filter=${this.currentFilter}`;

            if (this.currentFilter === "custom" && this.dateInput && this.dateInput.value) {
                url += `&date=${this.dateInput.value}`;
            }

            const resp = await auth.makeAuthenticatedRequest(url);
            if (!resp) throw new Error("Network error");
            if (!resp.ok) {
                const errJson = await resp.json().catch(() => ({}));
                throw new Error(errJson.error || `Server Error: ${resp.status}`);
            }

            const data = await resp.json();

            this.render(data);
        } catch (e) {
            console.error("App Usage Load Error:", e);
            const msg = e.message || "Failed to load data";
            this.tableBody.innerHTML = `<tr><td colspan="5" class="px-6 py-4 text-center text-red-500">Error: ${msg}</td></tr>`;
        }
    }

    render(records) {
        this.tableBody.innerHTML = "";

        if (!records || records.length === 0) {
            this.tableBody.parentElement.classList.add("hidden");
            this.emptyState.classList.remove("hidden");
            return;
        }

        this.tableBody.parentElement.classList.remove("hidden");
        this.emptyState.classList.add("hidden");

        records.forEach(r => {
            const startStr = window.formatDateTime(r.start_time);
            const endStr = window.formatDateTime(r.end_time);

            // Usage format (seconds to HH:MM:SS or just MM:SS)
            const usageFormatted = this.formatDuration(r.total_usage_seconds);

            const tr = document.createElement("tr");
            tr.className = "hover:bg-gray-50 transition-colors";

            tr.innerHTML = `
                <td class="px-4 py-3 sm:px-6 sm:py-4 whitespace-nowrap" data-label="User:">
                    <div class="font-medium text-gray-900">${r.user_name}</div>
                </td>
                <td class="px-4 py-3 sm:px-6 sm:py-4 whitespace-nowrap text-gray-500" data-label="Start:">
                    ${startStr}
                </td>
                <td class="px-4 py-3 sm:px-6 sm:py-4 whitespace-nowrap text-gray-500" data-label="End:">
                    ${endStr}
                </td>
                <td class="px-4 py-3 sm:px-6 sm:py-4 whitespace-nowrap" data-label="Duration:">
                    <span class="px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
                        ${usageFormatted}
                    </span>
                </td>
                <td class="px-4 py-3 sm:px-6 sm:py-4 whitespace-nowrap text-center" data-label="Actions:">
                    <button class="text-gray-400 hover:text-blue-600 transition-colors" onclick="window.appPerformanceManager.viewDetails(${r.id})">
                        <i class="fas fa-eye text-lg"></i>
                    </button>
                </td>
            `;

            // Store data for modal
            tr.dataset.record = JSON.stringify(r);
            this.tableBody.appendChild(tr);
        });

        this.recordsCache = records; // Simple caching for modal retrieval by ID
    }

    formatDuration(seconds) {
        if (!seconds) return "0s";
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;

        const parts = [];
        if (h > 0) parts.push(`${h}h`);
        if (m > 0) parts.push(`${m}m`);
        if (s > 0 || parts.length === 0) parts.push(`${s}s`);

        return parts.join(" ");
    }

    viewDetails(recordId) {
        const record = this.recordsCache.find(r => r.id === recordId);
        if (!record) return;

        const modal = document.getElementById("appUsageModal");
        const listContainer = document.getElementById("appUsageList");
        const title = document.getElementById("appUsageUserTime");

        if (!modal || !listContainer) return;

        // Set Title context
        title.textContent = `${record.user_name} • ${window.formatDateTime(record.start_time)}`;

        // Render Apps List
        listContainer.innerHTML = "";

        if (record.apps_data && Array.isArray(record.apps_data)) {
            // Sort by usage desc
            const sortedApps = [...record.apps_data].sort((a, b) => (b.usage_seconds || 0) - (a.usage_seconds || 0));

            sortedApps.forEach(app => {
                const duration = this.formatDuration(app.usage_seconds || 0);

                const item = document.createElement("div");
                item.className = "flex justify-between items-center p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors border border-gray-100";

                // Icon placeholder or generic
                item.innerHTML = `
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-full bg-white border border-gray-200 flex items-center justify-center text-gray-400 shadow-sm">
                            <i class="fas fa-cube"></i>
                        </div>
                        <div>
                            <p class="text-sm font-semibold text-gray-900">${app.app_name || 'Unknown App'}</p>
                            <p class="text-xs text-gray-400 font-mono">${app.package_name || ''}</p>
                        </div>
                    </div>
                    <div class="text-right">
                        <p class="text-sm font-bold text-gray-800">${duration}</p>
                    </div>
                `;
                listContainer.appendChild(item);
            });
        } else {
            listContainer.innerHTML = '<p class="text-center text-gray-500 py-4">No granular app data available.</p>';
        }

        modal.classList.remove("hidden");
    }
}
