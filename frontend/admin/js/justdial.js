
/**
 * JustDial Integration Manager
 * Handles connection, sync, and status display for JustDial.
 */
class JustDialManager {
    constructor() {
        this.statusBadge = document.getElementById('badge-jd-status');
        this.statusContainer = document.getElementById('jd-status-container');
        this.connectForm = document.getElementById('jd-connect-form');
        this.emailDisplay = document.getElementById('jd-email-display');
        this.lastSyncDisplay = document.getElementById('jd-last-sync-val');

        this.isConnected = false;
    }

    async init() {
        await this.checkStatus();
    }

    async checkStatus() {
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/justdial/status');
            if (resp && resp.ok) {
                const data = await resp.json();
                this.isConnected = data.is_connected;
                this.updateUI(data);
            }
        } catch (e) {
            console.error("Failed to check JustDial status:", e);
        }
    }

    updateUI(data) {
        if (this.isConnected) {
            // Show Connected State
            if (this.statusBadge) {
                this.statusBadge.textContent = "Connected";
                this.statusBadge.className = "px-3 py-1 bg-green-100 text-green-700 text-xs font-bold uppercase tracking-wider rounded-full";
            }
            if (this.statusContainer) this.statusContainer.classList.remove('hidden');
            if (this.connectForm) this.connectForm.classList.add('hidden');

            if (this.emailDisplay) this.emailDisplay.textContent = data.email_id || '-';

            if (this.lastSyncDisplay) {
                if (data.last_sync_time) {
                    const date = new Date(data.last_sync_time + 'Z');
                    this.lastSyncDisplay.textContent = date.toLocaleString();
                } else {
                    this.lastSyncDisplay.textContent = "Never";
                }
            }
        } else {
            // Show Connect Form
            if (this.statusBadge) {
                this.statusBadge.textContent = "Not Connected";
                this.statusBadge.className = "px-3 py-1 bg-gray-100 text-gray-500 text-xs font-bold uppercase tracking-wider rounded-full";
            }
            if (this.statusContainer) this.statusContainer.classList.add('hidden');
            if (this.connectForm) this.connectForm.classList.remove('hidden');
        }
    }

    async connect() {
        const email = document.getElementById('jd-email').value;
        const password = document.getElementById('jd-password').value;
        const btn = document.getElementById('btn-jd-connect');

        if (!email || !password) {
            alert("Please enter both Email and App Password.");
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Connecting...';
        }

        try {
            const resp = await auth.makeAuthenticatedRequest('/api/justdial/connect', {
                method: 'POST',
                body: JSON.stringify({ email, password })
            });

            if (resp && resp.ok) {
                alert("Connected successfully!");
                await this.checkStatus();
                // Optionally reload leads if integration leads might be there? 
                // Usually sync is needed first.
            } else {
                const err = await resp.json();
                alert("Connection Failed: " + (err.error || "Unknown Error"));
            }
        } catch (e) {
            alert("Error: " + e.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = 'Connect JustDial';
            }
        }
    }

    async sync() {
        const btn = document.getElementById('btn-jd-sync');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';
        }

        try {
            const resp = await auth.makeAuthenticatedRequest('/api/justdial/sync', {
                method: 'POST'
            });

            if (resp && resp.ok) {
                const data = await resp.json();
                alert(`Sync Complete! Added ${data.added} new leads.`);
                await this.checkStatus();
                // Reload Leads Table if on that page
                if (window.leadsManager && typeof window.leadsManager.loadLeads === 'function') {
                    window.leadsManager.loadLeads(1);
                }
            } else {
                const err = await resp.json();
                alert("Sync Failed: " + (err.message || err.error));
            }
        } catch (e) {
            alert("Error: " + e.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-sync-alt"></i> Sync Now';
            }
        }
    }

    async disconnect() {
        if (!confirm("Are you sure you want to disconnect JustDial integration?")) return;

        try {
            const resp = await auth.makeAuthenticatedRequest('/api/justdial/disconnect', {
                method: 'POST'
            });

            if (resp && resp.ok) {
                alert("Disconnected.");
                this.isConnected = false;
                window.location.reload();
            } else {
                alert("Failed to disconnect");
            }
        } catch (e) {
            alert("Error: " + e.message);
        }
    }
}

// Initialize
window.justDialManager = new JustDialManager();
