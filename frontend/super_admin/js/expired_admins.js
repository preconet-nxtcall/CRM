class ExpiredAdminsManager {
    constructor() {
        this.tableBody = document.getElementById("expired-admins-table-body");
    }

    async loadExpiredAdmins() {
        if (!this.tableBody) return;

        this.tableBody.innerHTML = `<tr><td colspan="5" class="px-6 py-4 text-center text-gray-500">Loading...</td></tr>`;

        try {
            const response = await auth.makeAuthenticatedRequest("/api/superadmin/expired-admins");

            if (!response || !response.ok) {
                this.tableBody.innerHTML = `<tr><td colspan="5" class="px-6 py-4 text-center text-red-500">Failed to load data</td></tr>`;
                return;
            }

            const data = await response.json();

            if (data.admins.length === 0) {
                this.tableBody.innerHTML = `<tr><td colspan="5" class="px-6 py-4 text-center text-gray-500">No expired admin accounts found.</td></tr>`;
                return;
            }

            this.renderAdmins(data.admins);

        } catch (error) {
            console.error("Error loading expired admins:", error);
            this.tableBody.innerHTML = `<tr><td colspan="5" class="px-6 py-4 text-center text-red-500">Error loading data</td></tr>`;
        }
    }

    renderAdmins(admins) {
        this.tableBody.innerHTML = admins.map(admin => `
            <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-6 py-4 font-medium text-gray-900" data-label="Name">${this.escapeHtml(admin.name)}</td>
                <td class="px-6 py-4 text-gray-500" data-label="Email">${this.escapeHtml(admin.email)}</td>
                <td class="px-6 py-4 text-gray-500" data-label="Date">${new Date(admin.expiry_date).toLocaleDateString()}</td>
                <td class="px-6 py-4" data-label="Status">
                    <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800">
                        Expired
                    </span>
                </td>
                <td class="px-6 py-4 text-right" data-label="Actions">
                     <button onclick="document.getElementById('menuAdmins').click();" 
                        class="text-indigo-600 hover:text-indigo-900 font-medium text-xs border border-indigo-600 px-3 py-1 rounded hover:bg-indigo-50 transition-colors uppercase">
                        Edit / Renew
                    </button>
                </td>
            </tr>
        `).join("");
    }

    escapeHtml(text) {
        if (!text) return "";
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
}

// Initialize
window.expiredAdminsManager = new ExpiredAdminsManager();
