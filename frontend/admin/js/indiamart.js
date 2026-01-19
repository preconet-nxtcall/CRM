class IndiamartManager {
    constructor() {
        this.statusContainer = document.getElementById("im-status-container");
        this.connectForm = document.getElementById("im-connect-form");
        this.connectBtn = document.getElementById("btn-im-connect");
        this.syncBtn = document.getElementById("btn-im-sync");
        this.mobileDisplay = document.getElementById("im-mobile-display");
        this.apiKeyDisplay = document.getElementById("im-apikey-display");
    }

    async init() {
        console.log("IndiaMART Manager Initialized");
        this.checkConnectionStatus();
    }

    async checkConnectionStatus() {
        try {
            const res = await auth.makeAuthenticatedRequest('/api/indiamart/status');
            if (res && res.ok) {
                const data = await res.json();
                if (data && data.connected) {
                    this.showConnected(data.settings);
                } else {
                    this.showDisconnected();
                }
            } else {
                this.showDisconnected();
            }
        } catch (e) {
            console.error("Error checking IndiaMART status", e);
            this.showDisconnected();
        }
    }

    async connect() {
        const mobile = document.getElementById("im-mobile").value;
        const apiKey = document.getElementById("im-apikey").value;

        if (!mobile || !apiKey) {
            auth.showNotification("Please enter both Mobile Number and API Key.", "error");
            return;
        }

        try {
            this.connectBtn.disabled = true;
            this.connectBtn.textContent = "Connecting...";

            const payload = {
                mobile_number: mobile,
                api_key: apiKey
            };

            const response = await auth.makeAuthenticatedRequest('/api/indiamart/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (response && response.ok) {
                auth.showNotification("Connected Successfully!", "success");
                // Reload to fetch full status or just update UI
                this.checkConnectionStatus();
            } else {
                const err = await response.json();
                auth.showNotification("Failed to connect: " + (err.error || "Unknown error"), "error");
            }
        } catch (e) {
            console.error("Error connecting IndiaMART", e);
            auth.showNotification("Failed to connect. Please check console.", "error");
        } finally {
            this.connectBtn.disabled = false;
            this.connectBtn.textContent = "Connect IndiaMART";
        }
    }

    async sync() {
        try {
            this.syncBtn.disabled = true;
            this.syncBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';

            const response = await auth.makeAuthenticatedRequest('/api/indiamart/sync', {
                method: 'POST'
            });

            if (response) {
                const data = await response.json();
                if (response.ok) {
                    auth.showNotification(`Sync Complete! Added: ${data.added}, Total Fetched: ${data.total_fetched}`, "success");
                    if (leadsManager) leadsManager.loadLeads(); // Refresh leads table if available
                } else {
                    auth.showNotification("Sync Error: " + (data.error || "Unknown error"), "error");
                }
            }
        } catch (e) {
            auth.showNotification("Sync Failed: " + e.message, "error");
        } finally {
            this.syncBtn.disabled = false;
            this.syncBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Sync Now';
        }
    }

    async disconnect() {
        if (confirm("Are you sure you want to disconnect IndiaMART? Lead sync will stop.")) {
            try {
                const resp = await auth.makeAuthenticatedRequest('/api/indiamart/disconnect', {
                    method: 'POST'
                });
                if (resp && resp.ok) {
                    auth.showNotification("Disconnected successfully", "success");
                    this.showDisconnected();
                    document.getElementById("im-mobile").value = "";
                    document.getElementById("im-apikey").value = "";
                } else {
                    auth.showNotification("Failed to disconnect", "error");
                }
            } catch (e) {
                console.error("Error disconnecting", e);
                auth.showNotification("Failed to disconnect.", "error");
            }
        }
    }

    showConnected(settings) {
        if (this.statusContainer) this.statusContainer.classList.remove("hidden");
        if (this.connectForm) this.connectForm.classList.add("hidden");

        if (this.mobileDisplay) this.mobileDisplay.textContent = settings.mobile_number;
        if (this.apiKeyDisplay) this.apiKeyDisplay.textContent = settings.api_key; // Shows masked
    }

    showDisconnected() {
        if (this.statusContainer) this.statusContainer.classList.add("hidden");
        if (this.connectForm) this.connectForm.classList.remove("hidden");
    }
}

// Export to window
window.indiamartManager = new IndiamartManager();
