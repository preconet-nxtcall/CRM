/* admin/js/admin.js */

/* ---------------------------------
   SAFE GLOBAL MANAGERS
---------------------------------- */
window.dashboard = window.dashboard || null;
window.usersManager = window.usersManager || null;
window.attendanceManager = window.attendanceManager || null;
window.callHistoryManager = window.callHistoryManager || null;
window.callAnalyticsManager = window.callAnalyticsManager || null;
window.performanceManager = window.performanceManager || null;

/* ---------------------------------
   SIDEBAR & MENU HANDLER
---------------------------------- */
document.addEventListener("DOMContentLoaded", () => {

    /* Sidebar elements */
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("overlay");
    const open = document.getElementById("openSidebar");
    const close = document.getElementById("closeSidebar");

    if (open) open.onclick = () => {
        sidebar.classList.add("active");
        overlay.classList.add("active");
    };

    if (close) close.onclick = () => {
        sidebar.classList.remove("active");
        overlay.classList.remove("active");
    };

    if (overlay) overlay.onclick = () => {
        sidebar.classList.remove("active");
        overlay.classList.remove("active");
    };

    /* Expose menu DOM elements needed by index.html main script */
    window.menuDashboard = document.getElementById("menuDashboard");
    window.menuUsers = document.getElementById("menuUsers");
    window.menuCreateUser = document.getElementById("menuCreateUser");
    window.menuAttendance = document.getElementById("menuAttendance");
    window.menuCallHistory = document.getElementById("menuCallHistory");
    window.menuCallAnalytics = document.getElementById("menuCallAnalytics");   // ✔ FIXED
    window.menuPerformance = document.getElementById("menuPerformance");

    /* Expose sections */
    window.sectionDashboard = document.getElementById("sectionDashboard");
    window.sectionUsers = document.getElementById("sectionUsers");
    window.sectionCreateUser = document.getElementById("sectionCreateUser");
    window.sectionAttendance = document.getElementById("sectionAttendance");
    window.sectionCallHistory = document.getElementById("sectionCallHistory");
    window.sectionCallAnalytics = document.getElementById("sectionCallAnalytics"); // ✔ FIXED
    window.sectionPerformance = document.getElementById("sectionPerformance");

    /* Logout button */
    window.logoutBtn = document.getElementById("logoutBtn");
});



