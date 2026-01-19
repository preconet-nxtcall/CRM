
class MagicbricksManager {
    constructor() {
        this.statusContainer = document.getElementById("mb-status-container");
        this.connectForm = document.getElementById("mb-connect-form");
        this.connectBtn = document.getElementById("btn-mb-connect");
        this.syncBtn = document.getElementById("btn-mb-sync");

        this.emailDisplay = document.getElementById("mb-email-display");
        this.hostDisplay = document.getElementById("mb-host-display");
        this.lastSyncDisplay = document.getElementById("mb-last-sync-display");
    }

    async init() {
        // Elements might not exist if modal not active, but we check anyway
        this.checkConnectionStatus();
    }

    async checkConnectionStatus() {
        try {
            const res = await auth.makeAuthenticatedRequest('/api/magicbricks/status');
            if (res && res.ok) {
                const data = await res.json();
                this.updateBadge(data.connected);

                if (data.connected && data.settings) {
                    this.showConnected(data.settings);
                } else {
                    this.showDisconnected();
                }
            } else {
                this.updateBadge(false);
                this.showDisconnected();
            }
        } catch (e) {
            console.error("Error checking Magicbricks status", e);
            this.showDisconnected();
        }
    }

    updateBadge(isConnected) {
        const badge = document.getElementById("badge-mb-status");
        if (badge) {
            if (isConnected) {
                badge.className = "px-3 py-1 bg-green-100 text-green-700 text-xs font-bold uppercase tracking-wider rounded-full";
                badge.textContent = "Connected";
            } else {
                badge.className = "px-3 py-1 bg-gray-100 text-gray-500 text-xs font-bold uppercase tracking-wider rounded-full";
                badge.textContent = "Not Connected";
            }
        }
    }

    async connect() {
        const email = document.getElementById("mb-email").value;
        const password = document.getElementById("mb-password").value;
        // const host = document.getElementById("mb-host").value || "imap.gmail.com"; // Hidden or default

        if (!email || !password) {
            auth.showNotification("Please enter Email and App Password.", "error");
            return;
        }

        try {
            this.connectBtn.disabled = true;
            this.connectBtn.textContent = "Connecting...";

            const payload = {
                email: email,
                app_password: password,
                imap_host: "imap.gmail.com" // Default to Gmail for now, can be dynamic later
            };

            const response = await auth.makeAuthenticatedRequest('/api/magicbricks/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (response && response.ok) {
                auth.showNotification("Connected Successfully!", "success");
                this.checkConnectionStatus();
            } else {
                const err = await response.json();
                auth.showNotification("Failed to connect: " + (err.error || "Unknown error"), "error");
            }
        } catch (e) {
            console.error("Error connecting Magicbricks", e);
            auth.showNotification("Failed to connect. Check credentials.", "error");
        } finally {
            if (this.connectBtn) {
                this.connectBtn.disabled = false;
                this.connectBtn.textContent = "Connect Magicbricks";
            }
        }
    }

    async sync() {
        try {
            if (this.syncBtn) {
                this.syncBtn.disabled = true;
                this.syncBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';
            }

            const response = await auth.makeAuthenticatedRequest('/api/magicbricks/sync', {
                method: 'POST'
            });

            if (response) {
                const data = await response.json();
                if (response.ok) {
                    auth.showNotification(`Sync Complete! Added: ${data.added}`, "success");
                    this.checkConnectionStatus(); // Update last sync time
                    if (leadsManager) leadsManager.loadLeads();
                } else {
                    auth.showNotification("Sync Error: " + (data.error || "Unknown error"), "error");
                }
            }
        } catch (e) {
            auth.showNotification("Sync Failed: " + e.message, "error");
        } finally {
            if (this.syncBtn) {
                this.syncBtn.disabled = false;
                this.syncBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Sync Now';
            }
        }
    }

    async disconnect() {
        if (confirm("Are you sure? This will stop lead sync.")) {
            try {
                const resp = await auth.makeAuthenticatedRequest('/api/magicbricks/disconnect', {
                    method: 'POST'
                });
                if (resp && resp.ok) {
                    auth.showNotification("Disconnected", "success");
                    this.showDisconnected();
                    this.updateBadge(false);
                    document.getElementById("mb-email").value = "";
                    document.getElementById("mb-password").value = "";
                }
            } catch (e) {
                auth.showNotification("Disconnect failed", "error");
            }
        }
    }

    showConnected(settings) {
        // Re-fetch elements in case they weren't there at init
        this.statusContainer = document.getElementById("mb-status-container");
        this.connectForm = document.getElementById("mb-connect-form");

        if (this.statusContainer) this.statusContainer.classList.remove("hidden");
        if (this.connectForm) this.connectForm.classList.add("hidden");

        const emailDisplay = document.getElementById("mb-email-display");
        if (emailDisplay) emailDisplay.textContent = settings.email_id;

        const lastSyncDisplay = document.getElementById("mb-last-sync-val");
        if (lastSyncDisplay) {
            if (settings.last_sync_time) {
                // Ensure UTC interpretation if string lacks TZ info
                let dateStr = settings.last_sync_time;
                if (!dateStr.endsWith("Z") && !dateStr.includes("+")) {
                    dateStr += "Z";
                }
                lastSyncDisplay.textContent = new Date(dateStr).toLocaleString('en-IN', {
                    day: 'numeric', month: 'short', year: 'numeric',
                    hour: '2-digit', minute: '2-digit', hour12: true
                });
            } else {
                lastSyncDisplay.textContent = "Never";
            }
        }
    }

    showDisconnected() {
        this.statusContainer = document.getElementById("mb-status-container");
        this.connectForm = document.getElementById("mb-connect-form");

        if (this.statusContainer) this.statusContainer.classList.add("hidden");
        if (this.connectForm) this.connectForm.classList.remove("hidden");
    }
}

window.magicbricksManager = new MagicbricksManager();
