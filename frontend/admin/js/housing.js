
/**
 * Housing Integration Manager
 * Handles connection, syncing, and status UI for Housing.com
 */
const HousingManager = class {
    constructor() {
        this.isConnected = false;
        this.init();
    }

    async init() {
        await this.checkStatus();
    }

    async checkStatus() {
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/housing/status');
            if (resp && resp.ok) {
                const data = await resp.json();
                this.isConnected = data.is_connected;
                this.updateUI(data);

                // Update Badge in Main Grid
                const badge = document.getElementById('badge-housing-status');
                if (badge) {
                    if (this.isConnected) {
                        badge.textContent = "Connected";
                        badge.className = "px-3 py-1 bg-green-100 text-green-700 text-xs font-bold uppercase tracking-wider rounded-full";
                    } else {
                        badge.textContent = "Not Connected";
                        badge.className = "px-3 py-1 bg-gray-100 text-gray-500 text-xs font-bold uppercase tracking-wider rounded-full";
                    }
                }
            }
        } catch (e) {
            console.error("Housing Status Check Failed", e);
        }
    }

    updateUI(data) {
        this.statusContainer = document.getElementById('housing-status-container');
        this.connectForm = document.getElementById('housing-connect-form');
        this.emailDisplay = document.getElementById('housing-email-display');
        this.lastSyncDisplay = document.getElementById('housing-last-sync-val');
        this.statusBadge = document.getElementById('badge-housing-status');

        if (this.isConnected) {
            // Show Connected State
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
            if (this.statusContainer) this.statusContainer.classList.add('hidden');
            if (this.connectForm) this.connectForm.classList.remove('hidden');
        }
    }

    async connect() {
        const email = document.getElementById('housing-email').value;
        const password = document.getElementById('housing-password').value;
        const btn = document.getElementById('btn-housing-connect');

        if (!email || !password) {
            alert("Please enter both Email and App Password.");
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Connecting...';
        }

        try {
            const resp = await auth.makeAuthenticatedRequest('/api/housing/connect', {
                method: 'POST',
                body: JSON.stringify({ email, password })
            });

            if (resp && resp.ok) {
                alert("Connected successfully!");
                await this.checkStatus();
            } else {
                const err = await resp.json();
                alert("Connection Failed: " + (err.error || "Unknown Error"));
            }
        } catch (e) {
            alert("Error: " + e.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = 'Connect Housing';
            }
        }
    }

    async sync() {
        const btn = document.getElementById('btn-housing-sync');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';
        }

        try {
            const resp = await auth.makeAuthenticatedRequest('/api/housing/sync', {
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
        if (!confirm("Are you sure you want to disconnect Housing? Syncing will stop.")) return;

        try {
            const resp = await auth.makeAuthenticatedRequest('/api/housing/disconnect', {
                method: 'POST'
            });

            if (resp && resp.ok) {
                this.isConnected = false;
                await this.checkStatus();
                alert("Disconnected.");
            }
        } catch (e) {
            alert("Error: " + e.message);
        }
    }
}

// Attach to window
window.housingManager = new HousingManager();
