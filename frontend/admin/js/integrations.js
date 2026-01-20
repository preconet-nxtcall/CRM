
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
        if (sectionId === 'sectionIntegrationsMagicbricks' && window.magicbricksManager) {
            if (typeof window.magicbricksManager.init === 'function') window.magicbricksManager.init();
        }
        if (sectionId === 'sectionIntegrations99acres' && window.ninetyNineAcresManager) {
            if (typeof window.ninetyNineAcresManager.init === 'function') window.ninetyNineAcresManager.init();
        }
    }

    showMainIntegrations() {
        // Hide Modals
        const fbSec = document.getElementById('sectionIntegrationsFacebook');
        const imSec = document.getElementById('sectionIntegrationsIndiamart');

        const mbSec = document.getElementById('sectionIntegrationsMagicbricks'); // ADDED
        const nnaSec = document.getElementById('sectionIntegrations99acres'); // ADDED
        if (fbSec) fbSec.classList.add('hidden-section');
        if (imSec) imSec.classList.add('hidden-section');
        if (mbSec) mbSec.classList.add('hidden-section'); // ADDED
        if (nnaSec) nnaSec.classList.add('hidden-section'); // ADDED

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
        this.updateMagicbricksBadge();
        this.updateNinetyNineAcresBadge();
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

    async updateMagicbricksBadge() {
        const badge = document.getElementById('badge-mb-status');
        if (!badge) return;
        badge.className = "px-3 py-1 bg-gray-100 text-gray-400 text-xs font-bold uppercase tracking-wider rounded-full animate-pulse";
        badge.textContent = "Checking...";
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/magicbricks/status');
            if (resp && resp.ok) {
                const data = await resp.json();
                if (data.connected) {
                    badge.textContent = "Connected";
                    badge.className = "px-3 py-1 bg-green-100 text-green-700 text-xs font-bold uppercase tracking-wider rounded-full";
                } else {
                    badge.textContent = "Not Connected";
                    badge.className = "px-3 py-1 bg-gray-100 text-gray-500 text-xs font-bold uppercase tracking-wider rounded-full";
                }
            } else { badge.textContent = "Error"; }
        } catch (e) { console.error("MB Status Check Failed", e); badge.textContent = "Error"; }
    }

    async updateNinetyNineAcresBadge() {
        const badge = document.getElementById('badge-nna-status');
        if (!badge) return;
        badge.className = "px-3 py-1 bg-gray-100 text-gray-400 text-xs font-bold uppercase tracking-wider rounded-full animate-pulse";
        badge.textContent = "Checking...";
        try {
            const resp = await auth.makeAuthenticatedRequest('/api/99acres/status');
            if (resp && resp.ok) {
                const data = await resp.json();
                if (data.connected) {
                    badge.textContent = "Connected";
                    badge.className = "px-3 py-1 bg-green-100 text-green-700 text-xs font-bold uppercase tracking-wider rounded-full";
                } else {
                    badge.textContent = "Not Connected";
                    badge.className = "px-3 py-1 bg-gray-100 text-gray-500 text-xs font-bold uppercase tracking-wider rounded-full";
                }
            } else { badge.textContent = "Error"; }
        } catch (e) { console.error("99acres Status Check Failed", e); badge.textContent = "Error"; }
    }
}
window.integrationsManager = new IntegrationsManager();
