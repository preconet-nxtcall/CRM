class FreeTrialsManager {
    constructor() {
        this.tableBody = document.getElementById("free-trials-table-body");
    }

    async loadTrials() {
        if (!this.tableBody) return;

        this.tableBody.innerHTML = `<tr><td colspan="7" class="px-6 py-4 text-center text-gray-500">Loading...</td></tr>`;

        try {
            const response = await auth.makeAuthenticatedRequest("/api/superadmin/free-trials");

            if (!response || !response.ok) {
                this.tableBody.innerHTML = `<tr><td colspan="7" class="px-6 py-4 text-center text-red-500">Failed to load data</td></tr>`;
                return;
            }

            const data = await response.json();

            if (data.length === 0) {
                this.tableBody.innerHTML = `<tr><td colspan="7" class="px-6 py-4 text-center text-gray-500">No free trial requests found.</td></tr>`;
                return;
            }

            this.renderTrials(data);

        } catch (error) {
            console.error("Error loading free trials:", error);
            this.tableBody.innerHTML = `<tr><td colspan="7" class="px-6 py-4 text-center text-red-500">Error loading data</td></tr>`;
        }
    }

    renderTrials(trials) {
        this.tableBody.innerHTML = trials.map(trial => `
            <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-6 py-4 font-medium text-gray-900" data-label="Name">${this.escapeHtml(trial.name)}</td>
                <td class="px-6 py-4 text-gray-500" data-label="Email">${this.escapeHtml(trial.work_email)}</td>
                <td class="px-6 py-4 text-gray-500" data-label="Company">${this.escapeHtml(trial.company_name)}</td>
                <td class="px-6 py-4 text-gray-500" data-label="Phone">${this.escapeHtml(trial.phone_number)}</td>
                <td class="px-6 py-4 text-gray-500" data-label="Date">${new Date(trial.created_at).toLocaleString()}</td>
                <td class="px-6 py-4" data-label="Status">
                    ${this.getStatusBadge(trial.status)}
                </td>
                <td class="px-6 py-4 text-right" data-label="Actions">
                    ${this.getActionButtons(trial)}
                </td>
            </tr>
        `).join("");
    }

    getStatusBadge(status) {
        if (!status) status = 'active'; // Default for old records
        const styles = {
            'active': 'bg-green-100 text-green-800',
            'expired': 'bg-gray-100 text-gray-800',
            'blocked': 'bg-red-100 text-red-800'
        };
        const activeStyle = styles[status] || 'bg-gray-100 text-gray-800';
        return `<span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${activeStyle}">
                    ${status.charAt(0).toUpperCase() + status.slice(1)}
                </span>`;
    }

    getActionButtons(trial) {
        if (trial.status === 'blocked') {
            return `
                <button onclick="window.freeTrialsManager.toggleBlock(${trial.id}, 'unblock')" 
                    class="text-green-600 hover:text-green-900 font-medium text-xs border border-green-600 px-3 py-1 rounded hover:bg-green-50 transition-colors uppercase">
                    Unblock Account
                </button>
            `;
        } else {
            return `
                <button onclick="window.freeTrialsManager.toggleBlock(${trial.id}, 'block')" 
                    class="text-red-600 hover:text-red-900 font-medium text-xs border border-red-600 px-3 py-1 rounded hover:bg-red-50 transition-colors uppercase">
                    Block Account
                </button>
            `;
        }
    }

    async toggleBlock(id, action) {
        if (!confirm(`Are you sure you want to ${action} this account?`)) return;

        try {
            const response = await auth.makeAuthenticatedRequest(`/api/superadmin/free-trials/${id}/block`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action })
            });

            if (response.ok) {
                // Reload list
                this.loadTrials();
                // Show notification
                const msg = action === 'block' ? 'Account blocked successfully' : 'Account unblocked successfully';
                alert(msg); // Or use a cleaner toast if available
            } else {
                const res = await response.json();
                alert("Error: " + (res.error || "Failed to update status"));
            }
        } catch (error) {
            console.error("Error updating status:", error);
            alert("An error occurred while updating status.");
        }
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
