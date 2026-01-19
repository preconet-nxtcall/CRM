
/* admin/js/integrations.js */

/* ---------------------------------
   UI MANAGER (Navigation Helpers)
--------------------------------- */
class UIManager {
    init() {
        console.log("UIManager initialized");
    }

    openSubSection(sectionId) {
        // Show Target Modal (Overlay)
        const target = document.getElementById(sectionId);
        if (target) {
            target.classList.remove('hidden-section');
        }

        // Init specific managers if needed
        if (sectionId === 'sectionIntegrationsFacebook' && window.facebookManager) {
            if (typeof window.facebookManager.init === 'function') window.facebookManager.init();
        }
        if (sectionId === 'sectionIntegrationsIndiamart' && window.indiamartManager) {
            if (typeof window.indiamartManager.init === 'function') window.indiamartManager.init();
        }
    }

    showMainIntegrations() {
        // Hide Modals
        const fbSec = document.getElementById('sectionIntegrationsFacebook');
        const imSec = document.getElementById('sectionIntegrationsIndiamart');
        const mbSec = document.getElementById('sectionIntegrationsMagicbricks'); // ADDED
        if (fbSec) fbSec.classList.add('hidden-section');
        if (imSec) imSec.classList.add('hidden-section');
        if (mbSec) mbSec.classList.add('hidden-section'); // ADDED

        // Refresh Badges
        if (window.integrationsManager) window.integrationsManager.init();
    }
}
window.uiManager = new UIManager();


/* ---------------------------------
   INTEGRATIONS MANAGER (Dashboard)
--------------------------------- */
class IntegrationsManager {
    async init() {
        console.log("Integrations Dashboard Loaded");
        this.updateFacebookBadge();
        this.updateIndiaMartBadge();
    }

    async updateFacebookBadge() {
        const badge = document.getElementById('badge-fb-status');
        if (!badge) return;

        // Set Loading State
        badge.className = "px-3 py-1 bg-gray-100 text-gray-400 text-xs font-bold uppercase tracking-wider rounded-full animate-pulse";
        badge.textContent = "Checking...";

        try {
            const resp = await auth.makeAuthenticatedRequest('/api/facebook/status');
            if (resp && resp.ok) {
                const data = await resp.json();
                if (data.connected) {
                    badge.textContent = "Connected";
                    badge.className = "px-3 py-1 bg-green-100 text-green-700 text-xs font-bold uppercase tracking-wider rounded-full";
                } else {
                    badge.textContent = "Not Connected";
                    badge.className = "px-3 py-1 bg-gray-100 text-gray-500 text-xs font-bold uppercase tracking-wider rounded-full";
                }
            } else {
                badge.textContent = "Error";
            }
        } catch (e) {
            console.error("FB Status Check Failed", e);
            badge.textContent = "Error";
        }
    }

    async updateIndiaMartBadge() {
        const badge = document.getElementById('badge-im-status');
        if (!badge) return;

        // Set Loading State
        badge.className = "px-3 py-1 bg-gray-100 text-gray-400 text-xs font-bold uppercase tracking-wider rounded-full animate-pulse";
        badge.textContent = "Checking...";

        try {
            const resp = await auth.makeAuthenticatedRequest('/api/indiamart/status');
            if (resp && resp.ok) {
                const data = await resp.json();
                if (data.connected) {
                    badge.textContent = "Connected";
                    badge.className = "px-3 py-1 bg-green-100 text-green-700 text-xs font-bold uppercase tracking-wider rounded-full";
                } else {
                    badge.textContent = "Not Connected";
                    badge.className = "px-3 py-1 bg-gray-100 text-gray-500 text-xs font-bold uppercase tracking-wider rounded-full";
                }
            } else {
                badge.textContent = "Error";
            }
        } catch (e) {
            console.error("IM Status Check Failed", e);
            badge.textContent = "Error";
        }
    }
}
window.integrationsManager = new IntegrationsManager();
