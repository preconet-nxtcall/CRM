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

        // Inject Auto Sync Toggle if not present
        let toggleContainer = document.getElementById("im-auto-sync-container");
        if (!toggleContainer && this.statusContainer) {
            const div = document.createElement("div");
            div.id = "im-auto-sync-container";
            div.className = "mt-4 pt-4 border-t border-gray-100 flex items-center justify-between";
            div.innerHTML = `
                <div>
                    <h4 class="text-sm font-medium text-gray-900">Automatic Sync</h4>
                    <p class="text-xs text-gray-500">Fetch leads automatically every 15 mins</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" id="im-auto-sync-checkbox" class="sr-only peer" onchange="indiamartManager.toggleAutoSync(this)">
                    <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                </label>
             `;
            // Append after the grid
            this.statusContainer.appendChild(div);
        }

        // Inject Last Sync Display if not present
        let lastSyncContainer = document.getElementById("im-last-sync-display");
        if (!lastSyncContainer && this.statusContainer) {
            const p = document.createElement("p");
            p.className = "text-sm text-gray-500 mt-2 text-center italic";
            p.innerHTML = 'Last Synced: <span id="im-last-sync-val">Never</span>';
            // Insert before the buttons
            const btns = this.statusContainer.querySelector(".flex.justify-center.gap-4");
            if (btns) this.statusContainer.insertBefore(p, btns);
            else this.statusContainer.appendChild(p);
        }

        // Update Values
        const checkbox = document.getElementById("im-auto-sync-checkbox");
        if (checkbox) checkbox.checked = settings.auto_sync_enabled;

        const lastSyncVal = document.getElementById("im-last-sync-val");
        if (lastSyncVal) {
            lastSyncVal.textContent = settings.last_sync_time ? new Date(settings.last_sync_time).toLocaleString('en-IN') : "Never";
        }
    }

    async toggleAutoSync(checkbox) {
        const enabled = checkbox.checked;
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/indiamart/update_settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ auto_sync: enabled })
            });

            if (resp && resp.ok) {
                auth.showNotification(`Auto Sync ${enabled ? 'Enabled' : 'Disabled'}`, "success");
            } else {
                checkbox.checked = !enabled; // Revert
                auth.showNotification("Failed to update settings", "error");
            }
        } catch (e) {
            checkbox.checked = !enabled; // Revert
            console.error("Error toggling auto sync", e);
            auth.showNotification("Error updating settings", "error");
        }
    }

    showDisconnected() {
        if (this.statusContainer) {
            this.statusContainer.classList.add("hidden");
            // Clean up toggle if exists logic not strictly needed as container is hidden
        }
        if (this.connectForm) this.connectForm.classList.remove("hidden");
    }
}

// Export to window
window.indiamartManager = new IndiamartManager();
