let currentLogPage = 1;
const logsPerPage = 20;

document.addEventListener("DOMContentLoaded", () => {
    const logsMenuButton = document.querySelector('[data-target="logs-view"]');
    if (logsMenuButton) {
        logsMenuButton.addEventListener("click", () => loadLogs());
    }

    const logFilter = document.getElementById("logFilter");
    if (logFilter) {
        logFilter.addEventListener("change", () => loadLogs());
    }
});

/* -------------------------------------------------------
    LOAD LOGS  (BACKEND HAS NO PAGINATION)
------------------------------------------------------- */
async function loadLogs() {
    try {
        let url = `/api/superadmin/logs`;

        const filterRole = document.getElementById("logFilter")?.value || "";

        const response = await auth.makeAuthenticatedRequest(url);
        const data = await response.json();

        if (!response.ok) {
            auth.showNotification(data.error || "Failed to load logs", "error");
            return;
        }

        let logs = data.logs || [];

        // Manual filter on frontend — because backend has no filter support
        if (filterRole) {
            logs = logs.filter(l => l.actor_role === filterRole);
        }

        displayLogs(logs);

    } catch (e) {
        console.error("Error loading logs:", e);
        auth.showNotification("Failed to load activity logs", "error");
    }
}

/* -------------------------------------------------------
    DISPLAY LOGS
------------------------------------------------------- */
function displayLogs(logs) {
    const tbody = document.getElementById("logsTableBody");
    if (!tbody) return;

    if (!logs || logs.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="py-10 text-center text-gray-500">
                    <i class="fas fa-history text-4xl text-gray-300 mb-3"></i>
                    <p>No activity logs found</p>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = logs.map(log => `
        <tr class="hover:bg-gray-50 transition">

            <td>${new Date(log.timestamp).toLocaleString()}</td>

            <td>
                <span class="px-3 py-1 rounded-full text-xs font-medium 
                    ${
                        log.actor_role === "super_admin"
                        ? "bg-purple-100 text-purple-700"
                        : log.actor_role === "admin"
                        ? "bg-blue-100 text-blue-700"
                        : "bg-green-100 text-green-700"
                    }">
                    ${log.actor_role.replace("_", " ").toUpperCase()}
                </span>
            </td>

            <td>${log.action}</td>
            <td>${log.target_type || "N/A"}</td>
            <td>${log.target_id || "N/A"}</td>

        </tr>
    `).join("");
}

/* -------------------------------------------------------
    PAGINATION REMOVED (Backend does not support it)
------------------------------------------------------- */
