class FacebookManager {
    constructor() {
        this.statusContainer = document.getElementById("fb-status-container");
        this.connectBtn = document.getElementById("btn-fb-connect");
        this.pageNameEl = document.getElementById("fb-page-name");
        this.pageIdEl = document.getElementById("fb-page-id-val");
    }

    async init() {
        console.log("Facebook Manager Initialized (Strict SaaS Mode)");
        this.checkConnectionStatus();
    }

    async checkConnectionStatus() {
        try {
            const res = await auth.makeAuthenticatedRequest('/api/facebook/status');
            if (res) {
                const data = await res.json();
                if (data && data.connected) {
                    this.showConnected(data.page);
                } else {
                    this.showDisconnected();
                }
            }
        } catch (e) {
            console.error("Error checking FB status", e);
            this.showDisconnected();
        }
    }

    async login() {
        // Step 1: Get Auth URL from Backend
        try {
            const res = await auth.makeAuthenticatedRequest('/api/facebook/auth/start');
            if (!res) return;
            const data = await res.json();

            if (data.url) {
                this.openAuthPopup(data.url);
            } else {
                alert("Failed to start Facebook Login");
            }
        } catch (e) {
            console.error("Login Start Error", e);
            alert("Error initiating login");
        }
    }

    openAuthPopup(url) {
        const width = 600;
        const height = 700;
        const left = (screen.width - width) / 2;
        const top = (screen.height - height) / 2;

        const popup = window.open(url, "Facebook Login", `width=${width},height=${height},top=${top},left=${left}`);

        // Listen for success message from popup
        const messageHandler = async (event) => {
            // Verify origin if possible, but strict-origin is usually safe here relative to same domain
            if (event.data && event.data.type === 'FB_AUTH_SUCCESS') {
                window.removeEventListener('message', messageHandler);
                // Popup usually closes itself or we can close it
                console.log("Auth Success Signal Received");
                this.fetchAndSelectPage();
            }
        };

        window.addEventListener('message', messageHandler);

        // Poll for popup closure as fallback
        const timer = setInterval(() => {
            if (popup.closed) {
                clearInterval(timer);
                // Can't distinguish cancel vs success easily without message, 
                // but user can click Connect again if it failed.
            }
        }, 1000);
    }

    async fetchAndSelectPage() {
        // Step 2: Fetch Pages (Backend uses Session Token)
        try {
            const res = await auth.makeAuthenticatedRequest('/api/facebook/pages');
            if (!res) return;
            const data = await res.json();

            if (data.error) {
                alert("Error fetching pages: " + data.error);
                return;
            }

            const pages = data.pages || [];
            if (pages.length === 0) {
                alert("No Facebook Pages found. You must be an Admin of a Page.");
                return;
            }

            this.promptPageSelection(pages);

        } catch (e) {
            console.error("Fetch Pages Error", e);
            alert("Failed to fetch pages");
        }
    }

    promptPageSelection(pages) {
        // Simple Prompt for MVP
        // Ideal: Custom Modal
        let msg = "Select a Facebook Page to Connect:\n";
        pages.forEach((p, i) => msg += `${i + 1}. ${p.name} (ID: ${p.id})\n`);

        const selection = prompt(msg, "1");
        if (!selection) return; // Cancelled

        const index = parseInt(selection) - 1;
        if (index >= 0 && index < pages.length) {
            this.connectPage(pages[index]);
        } else {
            alert("Invalid selection");
        }
    }

    async connectPage(page) {
        // Step 3: Connect (ID ONLY - Strict Contract)
        try {
            const payload = {
                page_id: page.id,
                page_name: page.name
            };

            const res = await auth.makeAuthenticatedRequest('/api/facebook/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res) {
                const data = await res.json();
                if (res.ok) {
                    alert("Facebook Connected Successfully!");
                    this.showConnected(page);
                } else {
                    alert("Connection Failed: " + (data.error || "Unknown Error"));
                }
            }
        } catch (e) {
            console.error("Connect Page Error", e);
            alert("Failed to connect page. It might be linked to another account.");
        }
    }

    async disconnect() {
        if (!confirm("Disconnect Facebook Page? Leads will stop syncing.")) return;

        try {
            const res = await auth.makeAuthenticatedRequest('/api/facebook/disconnect', { method: 'POST' });
            if (res && res.ok) {
                this.showDisconnected();
                alert("Disconnected");
            }
        } catch (e) {
            console.error("Disconnect Error", e);
        }
    }

    showConnected(page) {
        if (this.statusContainer) this.statusContainer.classList.remove("hidden");
        if (this.connectBtn) this.connectBtn.classList.add("hidden");
        if (this.pageNameEl) this.pageNameEl.textContent = page.name || "Connected Page";
        if (this.pageIdEl) this.pageIdEl.textContent = page.id || "";
    }

    showDisconnected() {
        if (this.statusContainer) this.statusContainer.classList.add("hidden");
        if (this.connectBtn) this.connectBtn.classList.remove("hidden");
    }
}

window.facebookManager = new FacebookManager();
