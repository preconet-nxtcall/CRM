/* admin/js/attendance.js */
class AttendanceManager {

  constructor() {
    this.loadUsersForFilter();
    this.initEventListeners();
  }

  initEventListeners() {
    const userFilter = document.getElementById("attendanceUserFilter");
    const dateFilter = document.getElementById("attendanceDateFilter");
    const monthFilter = document.getElementById("attendanceMonthFilter");
    const btnExport = document.getElementById("btnExportAttendance");

    const refresh = () => {
      this.loadAttendance(
        dateFilter?.value,
        userFilter?.value === 'all' ? null : userFilter?.value,
        1,
        25,
        monthFilter?.value
      );
    };

    if (userFilter) userFilter.addEventListener("change", refresh);
    if (dateFilter) dateFilter.addEventListener("change", refresh);
    if (monthFilter) monthFilter.addEventListener("change", refresh);

    if (btnExport) {
      btnExport.addEventListener("click", () => {
        this.exportAttendance();
      });
    }
  }

  // Standard interface for main.js
  load() {
    const userFilter = document.getElementById("attendanceUserFilter");
    const dateFilter = document.getElementById("attendanceDateFilter");
    const monthFilter = document.getElementById("attendanceMonthFilter");

    if (userFilter) userFilter.value = "all";
    // Default to empty
    if (dateFilter) dateFilter.value = "";
    if (monthFilter) monthFilter.value = "";

    this.loadAttendance();
  }

  async loadUsersForFilter() {
    try {
      const resp = await auth.makeAuthenticatedRequest('/api/admin/users?per_page=100');
      if (!resp || !resp.ok) return;
      const data = await resp.json();
      const users = data.users || [];

      const select = document.getElementById('attendanceUserFilter');
      if (!select) return;

      select.innerHTML = '<option value="all">All Users</option>';

      users.forEach(u => {
        const opt = document.createElement('option');
        opt.value = u.id;
        opt.textContent = u.name;
        select.appendChild(opt);
      });
    } catch (e) {
      console.error("Failed to load users for filter", e);
    }
  }

  async loadAttendance(date = null, user_id = null, page = 1, per_page = 25, month = null) {
    console.log("loadAttendance called with date:", date, "month:", month, "user:", user_id);
    try {
      let url = `/api/admin/attendance?page=${page}&per_page=${per_page}`;
      if (date) {
        url += `&date=${date}`;
      }
      if (month) {
        url += `&month=${month}`;
      }
      if (user_id && user_id !== 'all') {
        url += `&user_id=${user_id}`;
      }

      const resp = await auth.makeAuthenticatedRequest(url);

      if (!resp) return;
      const data = await resp.json();

      if (!resp.ok) {
        auth.showNotification(data.error || "Failed to load attendance", "error");
        return;
      }

      const items = data.attendance || [];
      const tableBody = document.getElementById("attendance-table-body");
      if (!tableBody) return;

      if (!items.length) {
        tableBody.innerHTML = `
          <tr>
            <td colspan="6" class="p-4 text-center text-gray-500">
              No attendance records found
            </td>
          </tr>
        `;
        // Clear pagination if no items
        const pagContainer = document.getElementById("attendance-pagination");
        if (pagContainer) pagContainer.innerHTML = "";
        return;
      }

      tableBody.innerHTML = items.map(a => `
        <tr class="table-row-hover">

          <!-- USER (Only Name) -->
          <td class="p-2 sm:p-3 font-medium text-gray-900 whitespace-nowrap" data-label="User:">
            ${a.user_name || "Unknown"}
          </td>

          <!-- CHECK IN -->
          <td class="p-2 sm:p-3 text-gray-700" data-label="Check In:">
            <div class="text-right">
              <div class="whitespace-nowrap font-medium text-gray-900">${window.formatDateTime(a.check_in)}</div>
              ${a.address ? `<div class="text-xs text-gray-500 mt-1 max-w-[200px] sm:max-w-[300px] ml-auto whitespace-normal break-words leading-tight">${a.address}</div>` : ''}
            </div>
          </td>

          <!-- CHECK OUT -->
          <td class="p-2 sm:p-3 text-gray-700" data-label="Check Out:">
            <div class="text-right">
              <div class="whitespace-nowrap font-medium text-gray-900">${window.formatDateTime(a.check_out)}</div>
              ${a.check_out_address ? `<div class="text-xs text-gray-500 mt-1 max-w-[200px] sm:max-w-[300px] ml-auto whitespace-normal break-words leading-tight">${a.check_out_address}</div>` : ''}
            </div>
          </td>

          <!-- STATUS -->
          <td class="p-2 sm:p-3 whitespace-nowrap" data-label="Status:">
            <span class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-full text-white text-xs sm:text-sm
              ${a.status === "present" ? "bg-green-500" : "bg-red-500"}">
              ${a.status}
            </span>
          </td>

          <!-- ACTIONS -->
          <td class="p-2 sm:p-3 whitespace-nowrap" data-label="Actions:">
            <div class="flex flex-col gap-1 text-xs">

              <!-- VIEW CHECK-IN IMAGE (if exists) -->
              ${a.image_path ? `
                <button onclick="attendanceManager.showImage('${a.image_path}')"
                  class="text-blue-600 hover:underline text-left">
                  View Image
                </button>
              ` : "-"}
              
              <!-- VIEW CHECK-OUT IMAGE (if exists) -->
              ${a.check_out_image ? `
                <button onclick="attendanceManager.showImage('${a.check_out_image}')"
                  class="text-purple-600 hover:underline text-left">
                  Checkout Image
                </button>
              ` : ""}

              <!-- OPEN MAP -->
              ${a.latitude && a.longitude ? `
                <a href="https://www.google.com/maps?q=${a.latitude},${a.longitude}"
                  target="_blank"
                  class="text-green-600 hover:underline">
                  Map
                </a>
              ` : ""}

            </div>
          </td>

        </tr>
      `).join("");


      // Render Pagination
      this.renderPagination(data.meta, date, user_id, month);

    } catch (e) {
      console.error(e);
      auth.showNotification("Failed to load attendance", "error");
    }
  }

  renderPagination(meta, date, user_id, month) {
    const container = document.getElementById("attendance-pagination");
    if (!container) return;
    if (!meta || meta.total <= meta.per_page) {
      container.innerHTML = "";
      return;
    }

    const currentPage = meta.page;
    const hasNext = meta.has_next;
    const hasPrev = meta.has_prev;

    container.innerHTML = `
      <div class="text-sm text-gray-600">
        Page ${currentPage} of ${meta.pages} (${meta.total} records)
      </div>
      <div class="flex gap-2 mt-2 sm:mt-0">
        <button id="btnAttPrev" class="px-3 py-1 text-sm border rounded hover:bg-gray-100 disabled:opacity-50" 
          ${!hasPrev ? "disabled" : ""}>
          Previous
        </button>
        <button id="btnAttNext" class="px-3 py-1 text-sm border rounded hover:bg-gray-100 disabled:opacity-50"
          ${!hasNext ? "disabled" : ""}>
          Next
        </button>
      </div>
    `;

    const btnPrev = document.getElementById("btnAttPrev");
    const btnNext = document.getElementById("btnAttNext");

    if (btnPrev && hasPrev) {
      btnPrev.addEventListener("click", () => {
        this.loadAttendance(date, user_id, currentPage - 1, 25, month);
      });
    }

    if (btnNext && hasNext) {
      btnNext.addEventListener("click", () => {
        this.loadAttendance(date, user_id, currentPage + 1, 25, month);
      });
    }
  }

  /* OPEN IMAGE PREVIEW */
  showImage(path) {
    console.log('🖼️ Attempting to show image:', path);

    if (!path) {
      console.error('❌ No image path provided');
      alert('No image available');
      return;
    }

    // Construct full URL
    const fullPath = `${window.location.origin}/${path}`;
    console.log('🔗 Full image URL:', fullPath);

    const modal = document.getElementById('imagePreviewModal');
    const img = document.getElementById('previewImage');

    if (modal && img) {
      img.src = fullPath;

      // Add error handler
      img.onerror = () => {
        console.error('❌ Image failed to load:', fullPath);
        alert(`Image not found: ${path}\n\nThis might mean:\n1. Image wasn't uploaded to server\n2. Image path is incorrect\n3. Image was deleted`);
        modal.classList.add('hidden');
      };

      img.onload = () => {
        console.log('✅ Image loaded successfully');
      };

      modal.classList.remove('hidden');
    } else {
      console.log('📂 Opening image in new tab');
      window.open(fullPath, "_blank");
    }
  }

  // Helper: Escape CSV values
  escapeCsv(val) {
    if (val === null || val === undefined) return "";
    const str = String(val);
    if (str.includes(",") || str.includes('"') || str.includes("\n")) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  }

  async exportAttendance() {
    const dateFilter = document.getElementById("attendanceDateFilter");
    const monthFilter = document.getElementById("attendanceMonthFilter");
    const userFilter = document.getElementById("attendanceUserFilter");

    const date = dateFilter ? dateFilter.value : null;
    const month = monthFilter ? monthFilter.value : null;
    const user_id = userFilter?.value === 'all' ? null : userFilter?.value;

    try {
      let url = `/api/admin/attendance/export_pdf?ignore=0`;
      if (date) url += `&date=${date}`;
      if (month) url += `&month=${month}`;
      if (user_id) url += `&user_id=${user_id}`;

      // auth.showNotification("Generating PDF...", "info");

      const resp = await auth.makeAuthenticatedRequest(url);
      if (!resp || !resp.ok) {
        auth.showNotification("Failed to fetch PDF", "error");
        return;
      }

      const blob = await resp.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = `Attendance_Report_${date || month || "all"}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);

      auth.showNotification("Download started", "success");

    } catch (e) {
      console.error("Export failed", e);
      auth.showNotification("Export failed: " + e.message, "error");
    }
  }
}

// Attach to window
window.AttendanceManager = AttendanceManager;
