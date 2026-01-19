/* ================================
        AUTH UTILITIES (ADMIN PANEL)
   ================================= */

class Auth {
    constructor() {
        this.tokenKey = "admin_token";
        this.userKey = "admin_user";
        this.emailKey = "admin_email";
    }

    /* ---------------------------------
        SAVE LOGIN (TOKEN + USER DATA)
    --------------------------------- */
    saveLogin(token, user) {
        localStorage.setItem(this.tokenKey, token);
        localStorage.setItem(this.userKey, JSON.stringify(user));

        if (user?.email) {
            localStorage.setItem(this.emailKey, user.email);
        }
    }

    /* ---------------------------------
        GET TOKEN
    --------------------------------- */
    getToken() {
        return localStorage.getItem(this.tokenKey);
    }

    /* ---------------------------------
        CURRENT USER DATA
    --------------------------------- */
    getCurrentUser() {
        const raw = localStorage.getItem(this.userKey);
        return raw ? JSON.parse(raw) : null;
    }

    /* ---------------------------------
        LOGOUT
    --------------------------------- */
    logout() {
        localStorage.removeItem(this.tokenKey);
        localStorage.removeItem(this.userKey);
        window.location.href = "/login";
    }

    /* ---------------------------------
        REMEMBER EMAIL
    --------------------------------- */
    getRememberedEmail() {
        return localStorage.getItem(this.emailKey) || "";
    }

    /* ---------------------------------
        SANITIZE URL → Prevent API prefix errors
    --------------------------------- */
    fixUrl(url) {
        let finalUrl = url;

        // Add leading slash
        if (!finalUrl.startsWith("/")) {
            finalUrl = "/" + finalUrl;
        }

        // Prefix /api only if not already present
        if (!finalUrl.startsWith("/api")) {
            finalUrl = "/api" + finalUrl;
        }

        return finalUrl;
    }

    /* ---------------------------------
        AUTHENTICATED REQUEST WRAPPER
    --------------------------------- */
    async makeAuthenticatedRequest(url, options = {}) {
        const token = this.getToken();

        if (!token) {
            this.showNotification("Please login again", "error");
            this.logout();
            return;
        }

        const finalUrl = this.fixUrl(url);

        const headers = {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
            ...(options.headers || {})
        };

        let resp;

        try {
            resp = await fetch(finalUrl, {
                ...options,
                headers,
            });
        } catch (err) {
            this.showNotification("Network error. Check server.", "error");
            console.error("Critical API Error:", err);
            return null;
        }

        if (resp.status === 401) {
            this.showNotification("Session expired — login again", "error");
            this.logout();
            return;
        }

        if (resp.status === 403) {
            let msg = "Access denied: Subscription Expired or Inactive";
            try {
                const errData = await resp.clone().json(); // Clone because body might be read again
                if (errData && errData.error) {
                    msg = errData.error;
                }
            } catch (e) {
                console.warn("Could not parse 403 error body", e);
            }

            this.showNotification(msg, "error");
            // Only logout if it's truly a session/subscription issue? 
            // For now, keep logout behavior but maybe delay it or conditionalize it.
            // Actually, if it's just "Unauthorized role", we shouldn't logout.
            if (msg.toLowerCase().includes("expired") || msg.toLowerCase().includes("inactive") || msg.toLowerCase().includes("blocked")) {
                setTimeout(() => this.logout(), 2000);
            }
            return null;
        }

        if (resp.status >= 500) {
            this.showNotification("Server error! Please try later", "error");
            console.error("Server error:", resp);
        }

        return resp;
    }

    /* ---------------------------------
        NOTIFICATION SYSTEM
    --------------------------------- */
    showNotification(message, type = "info") {
        let area = document.getElementById("notificationArea");

        if (!area) {
            area = document.createElement("div");
            area.id = "notificationArea";
            area.className = "fixed top-5 right-5 z-50 space-y-3";
            document.body.appendChild(area);
        }

        const palette = {
            success: "bg-green-600",
            error: "bg-red-600",
            info: "bg-blue-600",
            warning: "bg-yellow-500"
        };

        const div = document.createElement("div");
        div.className = `
            text-white px-4 py-3 rounded shadow-lg flex items-center gap-3 
            transition-all duration-300
            ${palette[type] || palette.info}
        `;
        div.innerHTML = `
            <i class="fas fa-circle-info"></i>
            <span>${message}</span>
        `;

        area.appendChild(div);

        setTimeout(() => {
            div.classList.add("opacity-0");
            setTimeout(() => div.remove(), 300);
        }, 3000);
    }
}

// GLOBAL INSTANCE
const auth = new Auth();
window.auth = auth;

/* ---------------------------------
   AUTO REDIRECT (FOR ALL ADMIN PAGES)
---------------------------------- */

document.addEventListener("DOMContentLoaded", () => {
    const isLoginPage = window.location.pathname.includes("login");

    // If NOT on login page AND token is missing → redirect
    if (!isLoginPage && !auth.getToken()) {
        window.location.href = "/";
    }

    // Auto-fill remembered email
    if (isLoginPage) {
        const emailField = document.getElementById("email");
        if (emailField) {
            emailField.value = auth.getRememberedEmail();
        }
    }
    // Force check on back/forward navigation (BFCache)
    window.addEventListener('pageshow', (event) => {
        if (event.persisted || (window.performance && window.performance.navigation.type === 2)) {
            if (!isLoginPage && !auth.getToken()) {
                window.location.href = "/";
            }
            if (isLoginPage && auth.getToken()) {
                window.location.href = "/admin/index.html";
            }
        }
    });
});
