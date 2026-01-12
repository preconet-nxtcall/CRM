/* js/main.js */

document.addEventListener("DOMContentLoaded", () => {
    console.log("Admin Panel Loaded");

    // ---------------------------------
    // THEME HANDLING (Night Mode)
    // ---------------------------------
    const themeToggleBtn = document.getElementById("themeToggle");
    const themeIcon = themeToggleBtn ? themeToggleBtn.querySelector("i") : null;

    // Load saved theme
    if (localStorage.getItem("theme") === "dark") {
        document.body.classList.add("dark-mode");
        if (themeIcon) {
            themeIcon.classList.remove("fa-moon");
            themeIcon.classList.add("fa-sun");
        }
        if (themeToggleBtn) {
            themeToggleBtn.innerHTML = '<i class="fas fa-sun mr-1"></i> Light Mode';
        }
    }

    // Toggle Event
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            document.body.classList.toggle("dark-mode");

            if (document.body.classList.contains("dark-mode")) {
                localStorage.setItem("theme", "dark");
                themeToggleBtn.innerHTML = '<i class="fas fa-sun mr-1"></i> Light Mode';
            } else {
                localStorage.setItem("theme", "light");
                themeToggleBtn.innerHTML = '<i class="fas fa-moon mr-1"></i> Night Mode';
            }
        });
    }

    // ---------------------------------
    // 0. GLOBAL HELPERS
    // ---------------------------------
    window.formatDateTime = (dateString) => {
        if (!dateString) return '-';

        // Treat input as Local Time (browser default for naive ISO)
        let date = new Date(dateString);

        // Check for invalid date
        if (isNaN(date.getTime())) {
            return dateString;
        }

        // Return formatted string in User's Local Time
        return date.toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: 'numeric',
            hour12: true
        });
    };

    // ---------------------------------
    // 0. INITIALIZATION (Moved top for Nav)
    // ---------------------------------
    window.dashboard = new DashboardManager();
    // window.usersManager is already initialized in users.js
    window.attendanceManager = new AttendanceManager();
    window.callHistoryManager = new CallHistoryManager();
    window.callAnalyticsManager = new CallAnalyticsManager();
    window.performanceManager = new PerformanceManager();
    window.appPerformanceManager = new AppPerformanceManager();
    // facebookManager is initialized in its own file (window.facebookManager = new ...)

    // Load Dashboard by default
    if (window.dashboard) {
        window.dashboard.loadStats();
    }

    // ---------------------------------
    // LOAD ADMIN PROFILE IN SIDEBAR
    // ---------------------------------
    const currentUser = auth.getCurrentUser();
    if (currentUser) {
        const nameEl = document.getElementById('sidebarUserName');
        const emailEl = document.getElementById('sidebarUserEmail');

        if (nameEl) {
            nameEl.textContent = currentUser.name || currentUser.email || 'Admin User';
        }
        if (emailEl) {
            emailEl.textContent = currentUser.email || 'admin@example.com';
        }
    }

    // ---------------------------------
    // 1. SIDEBAR TOGGLE
    // ---------------------------------
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("overlay");
    const openBtn = document.getElementById("openSidebar");
    const closeBtn = document.getElementById("closeSidebar");

    function toggleSidebar(show) {
        if (show) {
            sidebar.classList.add("active");
            overlay.classList.add("active");
        } else {
            sidebar.classList.remove("active");
            overlay.classList.remove("active");
        }
    }

    if (openBtn) openBtn.onclick = () => toggleSidebar(true);
    if (closeBtn) closeBtn.onclick = () => toggleSidebar(false);
    if (overlay) overlay.onclick = () => toggleSidebar(false);


    // ---------------------------------
    // 2. NAVIGATION HANDLER
    // ---------------------------------
    const navItems = [
        { id: "menuDashboard", mobileId: "mobileNavHome", section: "sectionDashboard", title: "Dashboard", manager: window.dashboard },
        { id: "menuCallAnalytics", mobileId: "mobileNavAnalytics", section: "sectionCallAnalytics", title: "Call Analytics", manager: window.callAnalyticsManager },
        { id: "menuPerformance", section: "sectionPerformance", title: "Performance", manager: window.performanceManager },
        { id: "menuUsers", mobileId: "mobileNavUsers", section: "sectionUsers", title: "User Management", manager: window.usersManager },
        { id: "menuCreateUser", section: "sectionCreateUser", title: "Create User", manager: null }, // No manager needed for form
        { id: "menuAttendance", section: "sectionAttendance", title: "Attendance Records", manager: window.attendanceManager },
        { id: "menuCallHistory", mobileId: "mobileNavCalls", section: "sectionCallHistory", title: "Call Logs", manager: window.callHistoryManager },
        { id: "menuAppPerformance", section: "sectionAppPerformance", title: "App Usage Monitor", manager: window.appPerformanceManager },
        { id: "menuFollowup", section: "sectionFollowup", title: "Follow-ups", manager: window.followupManager },
        { id: "menuLeads", section: "sectionLeads", title: "Leads Management", manager: window.leadsManager },
        { id: "menuIntegrations", mobileId: null, section: "sectionIntegrations", title: "Facebook Integration", manager: window.facebookManager }
    ];

    const pageTitle = document.getElementById("pageTitle");

    function activateSection(item) {
        // 1. Hide all sections
        navItems.forEach(nav => {
            const sec = document.getElementById(nav.section);
            if (sec) sec.classList.add("hidden-section");

            const menu = document.getElementById(nav.id);
            if (menu) {
                menu.classList.remove("bg-blue-600", "text-white", "shadow-md");
                menu.classList.add("text-gray-300", "hover:bg-gray-800", "hover:text-white");

                // Reset icon color
                const icon = menu.querySelector("i");
                if (icon) {
                    icon.classList.remove("text-blue-200");
                    icon.classList.add("text-gray-400");
                }
            }

            // Reset mobile nav
            if (nav.mobileId) {
                const mobMenu = document.getElementById(nav.mobileId);
                if (mobMenu) mobMenu.classList.remove("active");
            }
        });

        // 2. Show target section
        const targetSec = document.getElementById(item.section);
        if (targetSec) targetSec.classList.remove("hidden-section");

        // 3. Highlight menu item
        const targetMenu = document.getElementById(item.id);
        if (targetMenu) {
            targetMenu.classList.remove("text-gray-300", "hover:bg-gray-800", "hover:text-white");
            targetMenu.classList.add("bg-blue-600", "text-white", "shadow-md");

            const icon = targetMenu.querySelector("i");
            if (icon) {
                icon.classList.remove("text-gray-400");
                icon.classList.add("text-blue-200");
            }
        }

        // Highlight mobile nav
        if (item.mobileId) {
            const mobMenu = document.getElementById(item.mobileId);
            if (mobMenu) mobMenu.classList.add("active");
        }

        // 4. Update Title
        if (pageTitle) pageTitle.textContent = item.title;

        // 5. Initialize/Load Data if Manager exists
        if (item.manager && typeof item.manager.init === 'function') {
            item.manager.init();
        } else if (item.manager && typeof item.manager.load === 'function') {
            item.manager.load();
        }

        // Special case for Dashboard (it might use loadStats)
        if (item.id === "menuDashboard" && window.dashboard) {
            window.dashboard.loadStats();
        }

        // Close sidebar on mobile
        if (window.innerWidth < 1024) {
            toggleSidebar(false);
        }
    }

    // Attach Click Events
    navItems.forEach(item => {
        const el = document.getElementById(item.id);
        if (el) {
            el.addEventListener("click", () => activateSection(item));
        }

        if (item.mobileId) {
            const mobEl = document.getElementById(item.mobileId);
            if (mobEl) {
                mobEl.addEventListener("click", (e) => {
                    e.preventDefault();
                    activateSection(item);
                });
            }
        }
    });






    // Set current date
    const dateEl = document.getElementById("currentDate");
    if (dateEl) {
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        dateEl.textContent = new Date().toLocaleDateString('en-US', options);
    }

    // Logout Handler
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            if (confirm("Are you sure you want to logout?")) {
                auth.logout();
            }
        });
    }

});
