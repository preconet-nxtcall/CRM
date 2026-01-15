class FacebookManager {
    constructor() {
        this.statusContainer = document.getElementById("fb-status-container");
        this.connectBtn = document.getElementById("btn-fb-connect");
        this.pageNameEl = document.getElementById("fb-page-name");
        this.pageIdEl = document.getElementById("fb-page-id-val");
        this.pageImgEl = document.getElementById("fb-page-img");
    }

    async init() {
        console.log("Facebook Manager Initialized");
        // Load Facebook SDK asynchronously
        this.loadFacebookSDK();
        this.checkConnectionStatus();
    }

    loadFacebookSDK() {
        if (document.getElementById('facebook-jssdk')) return;

        window.fbAsyncInit = function () {
            FB.init({
                appId: '1537220340728257', // New Business App ID
                cookie: true,
                xfbml: true,
                version: 'v24.0'
            });
            console.log("FB SDK Loaded");
        };

        (function (d, s, id) {
            var js, fjs = d.getElementsByTagName(s)[0];
            if (d.getElementById(id)) { return; }
            js = d.createElement(s); js.id = id;
            js.src = "https://connect.facebook.net/en_US/sdk.js";
            fjs.parentNode.insertBefore(js, fjs);
        }(document, 'script', 'facebook-jssdk'));
    }

    async checkConnectionStatus() {
        try {
            // Using auth.makeAuthenticatedRequest from auth.js, which handles the Token
            const res = await auth.makeAuthenticatedRequest('/api/facebook/status');

            // `makeAuthenticatedRequest` returns the Response object, we need to parse JSON
            // But checking auth.js, it returns `resp` which is the fetch response object (or null).
            // Wait, looking at auth.js: `return resp;`. So we need to await .json().
            if (res) {
                const data = await res.json();
                if (data && data.connected) {
                    this.showConnected(data.page);
                } else {
                    this.showDisconnected();
                }
            } else {
                this.showDisconnected();
            }
        } catch (e) {
            console.error("Error checking FB status", e);
            this.showDisconnected();
        }
    }

    login() {
        if (!window.FB) {
            alert("Facebook SDK not loaded yet. Please wait or refresh.");
            return;
        }

        FB.login((response) => {
            if (response.authResponse) {
                console.log("Granted Scopes:", response.authResponse.grantedScopes);
                this.handleLoginSuccess(response.authResponse);
            } else {
                console.log("User cancelled login or did not fully authorize.");
            }
        }, {
            scope: 'pages_show_list,leads_retrieval',
            auth_type: 'reauthenticate',
            return_scopes: true
        });
    }

    async handleLoginSuccess(authResponse) {
        console.log("FB Login Success", authResponse);
        const userAccessToken = authResponse.accessToken;

        // Fetch User's Pages via FB Client SDK
        FB.api('/me/accounts', async (response) => {
            if (response && !response.error) {
                const pages = response.data;
                if (pages.length === 0) {
                    alert("No Facebook Pages found for this account.");
                    return;
                }

                // For MVP: Auto-select the first page or let user choose if easy
                let selectedPage = pages[0];

                if (pages.length > 1) {
                    // Simple select mechanic: Name mapping
                    let msg = "Found multiple pages:\n";
                    pages.forEach((p, i) => msg += `${i + 1}. ${p.name}\n`);
                    msg += "Enter the number of the page to connect:";
                    const selection = prompt(msg, "1");
                    const index = parseInt(selection) - 1;
                    if (index >= 0 && index < pages.length) {
                        selectedPage = pages[index];
                    }
                }

                await this.connectPageToBackend(selectedPage);

            } else {
                console.error("Error fetching pages", response.error);
                alert("Failed to fetch pages from Facebook: " + (response.error ? response.error.message : "Unknown error"));
            }
        });
    }

    async connectPageToBackend(page) {
        try {
            const payload = {
                page_id: page.id,
                page_name: page.name,
                page_access_token: page.access_token
            };

            const response = await auth.makeAuthenticatedRequest('/api/facebook/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (response) {
                const data = await response.json();
                if (data && data.message) {
                    alert("Connected Successfully!");
                    this.showConnected({ name: page.name, id: page.id });
                }
            }
        } catch (e) {
            console.error("Error connecting page", e);
            alert("Failed to connect page. It might be linked to another account.");
        }
    }

    async disconnect() {
        if (confirm("Are you sure you want to disconnect your Facebook Page? Lead sync will stop.")) {
            try {
                const resp = await auth.makeAuthenticatedRequest('/api/facebook/disconnect', {
                    method: 'POST'
                });
                if (resp && resp.ok) {
                    this.showDisconnected();
                    window.location.reload();
                }
            } catch (e) {
                console.error("Error disconnecting", e);
                alert("Failed to disconnect.");
            }
        }
    }

    showConnected(page) {
        if (this.statusContainer) this.statusContainer.classList.remove("hidden");
        if (this.connectBtn) this.connectBtn.classList.add("hidden");

        if (this.pageNameEl) this.pageNameEl.textContent = page.name;
        if (this.pageIdEl) this.pageIdEl.textContent = page.id;
        // this.pageImgEl.style.backgroundImage = `url(...)`; // Optional: Fetch page picture if needed
    }

    showDisconnected() {
        if (this.statusContainer) this.statusContainer.classList.add("hidden");
        if (this.connectBtn) this.connectBtn.classList.remove("hidden");
    }
}

// Export to window
window.facebookManager = new FacebookManager();
