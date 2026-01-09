/************************************************************
 * SUPER ADMIN DASHBOARD CONTROLLER
 ************************************************************/
class DashboardManager {
    constructor() {
        this.stats = null;
        // Navigation is handled in index.html now
    }

    /************************************************************
     * LOAD DASHBOARD STATS
     ************************************************************/
    async loadStats() {
        try {
            console.log("DEBUG: Fetching dashboard stats...");

            const response = await auth.makeAuthenticatedRequest("/api/superadmin/dashboard-stats");
            const data = await response.json();

            if (response.ok) {
                this.stats = data.stats;

                // Update Sidebar Super Admin Profile
                const saNameEl = document.getElementById('sidebar-super-admin-name');
                const saEmailEl = document.getElementById('sidebar-super-admin-email');

                if (saNameEl && this.stats.super_admin_name) {
                    saNameEl.textContent = this.stats.super_admin_name;
                }
                if (saEmailEl && this.stats.super_admin_email) {
                    saEmailEl.textContent = this.stats.super_admin_email;
                }

                this.renderStats();
                // Also load recent activity when loading dashboard
                this.loadRecentActivity();
            } else {
                auth.showNotification(data.error || "Failed to load dashboard stats", "error");
            }

        } catch (error) {
            console.error("ERROR Loading Stats:", error);
            auth.showNotification("Error loading dashboard stats", "error");
        }
    }

    /************************************************************
     * RENDER STATS CARDS
     ************************************************************/
    renderStats() {
        const container = document.getElementById("stats-cards");
        if (!container || !this.stats) return;

        const cards = [
            {
                label: "Total Admins",
                value: this.stats.total_admins || 0,
                icon: "users-cog",
                color: "text-blue-600",
                bg: "bg-blue-50"
            },
            {
                label: "Total Users",
                value: this.stats.total_users || 0,
                icon: "users",
                color: "text-green-600",
                bg: "bg-green-50"
            },
            {
                label: "Active Admins",
                value: this.stats.active_admins || 0,
                icon: "user-check",
                color: "text-emerald-600",
                bg: "bg-emerald-50"
            },
            {
                label: "Expired Admins",
                value: this.stats.expired_admins || 0,
                icon: "exclamation-circle",
                color: "text-red-600",
                bg: "bg-red-50"
            }
        ];

        container.innerHTML = cards
            .map(card => `
                <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover-card">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-sm font-medium text-gray-500">${card.label}</p>
                            <p class="text-3xl font-bold text-gray-900 mt-2">${card.value}</p>
                        </div>
                        <div class="${card.bg} w-12 h-12 rounded-xl flex items-center justify-center shadow-sm">
                            <i class="fas fa-${card.icon} ${card.color} text-xl"></i>
                        </div>
                    </div>
                </div>
            `)
            .join("");
    }

    /************************************************************
     * LOAD RECENT ACTIVITY
     ************************************************************/
    async loadRecentActivity() {
        try {
            const response = await auth.makeAuthenticatedRequest("/api/superadmin/logs");
            const data = await response.json();

            if (response.ok) {
                this.renderRecentActivity(data.logs || []);
            }

        } catch (error) {
            console.error("ERROR Loading Activity:", error);
        }
    }

    /************************************************************
     * RENDER RECENT ACTIVITY (Right Side Panel)
     ************************************************************/
    renderRecentActivity(logs) {
        const container = document.getElementById("recent-activity");
        if (!container) return;

        if (logs.length === 0) {
            container.innerHTML = `
                <div class="text-center text-gray-500 py-10">
                    <i class="fas fa-history text-3xl text-gray-300 mb-2"></i>
                    <p>No recent activity</p>
                </div>
            `;
            return;
        }

        container.innerHTML = logs.map(log => {
            // Determine styles based on Role and Action
            let icon = 'history';
            let bgClass = 'bg-gray-100 text-gray-600';

            const actionLower = log.action_type.toLowerCase();
            const isSuperAdmin = log.role === 'super_admin';

            if (isSuperAdmin) {
                bgClass = 'bg-purple-100 text-purple-600';
                icon = 'shield-alt';
            } else if (actionLower.includes('create')) {
                bgClass = 'bg-green-100 text-green-600';
                icon = 'user-plus';
            } else if (actionLower.includes('delete')) {
                bgClass = 'bg-red-100 text-red-600';
                icon = 'trash-alt';
            } else if (actionLower.includes('update') || actionLower.includes('block')) {
                bgClass = 'bg-blue-100 text-blue-600';
                icon = 'edit';
            } else {
                bgClass = 'bg-blue-50 text-blue-600';
                icon = 'clipboard-list';
            }

            return `
            <div class="flex items-start space-x-3 p-3 rounded-lg hover:bg-gray-50 transition border-b border-gray-50 last:border-0">
                <div class="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center ${bgClass}">
                    <i class="fas fa-${icon} text-xs"></i>
                </div>

                <div class="min-w-0 flex-1">
                    <div class="flex justify-between items-start">
                        <p class="text-sm font-bold text-gray-900 truncate">${log.admin_name}</p>
                        <span class="text-[10px] text-gray-400 whitespace-nowrap ml-2">${this.formatTime(log.timestamp)}</span>
                    </div>
                    <p class="text-xs text-gray-600 mt-0.5 break-words">
                        ${log.action_type}
                    </p>
                </div>
            </div>
            `;
        }).join("");
    }

    getIcon(action) {
        if (!action) return "history";
        const a = action.toLowerCase();
        if (a.includes("create")) return "plus";
        if (a.includes("delete")) return "trash";
        if (a.includes("update")) return "pen";
        if (a.includes("login")) return "sign-in-alt";
        if (a.includes("logout")) return "sign-out-alt";
        return "history";
    }

    formatTime(timestamp) {
        if (!timestamp) return "Unknown";
        const d = new Date(timestamp);
        return d.toLocaleString();
    }
}
