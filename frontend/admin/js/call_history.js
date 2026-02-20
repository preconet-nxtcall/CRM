/* admin/js/call_history.js */

class CallHistoryManager {

  constructor() {
    this.loadUsersForFilter();
    this.initEventListeners();
  }

  initEventListeners() {
    const userFilter = document.getElementById('callUserFilter');
    const dateFilter = document.getElementById('callDateFilter'); // Not currently in HTML but good to keep if added later
    const searchInput = document.getElementById('callSearchInput');
    const typeFilter = document.getElementById('callTypeFilter');
    const btnExport = document.getElementById('btnExportCalls');

    const refresh = () => {
      this.loadCalls(
        userFilter?.value === 'all' ? null : userFilter?.value,
        1,
        50,
        "",
        dateFilter?.value,
        searchInput?.value,
        typeFilter?.value
      );
    };

    if (userFilter) userFilter.addEventListener('change', refresh);
    if (dateFilter) dateFilter.addEventListener('change', refresh);
    const monthFilter = document.getElementById('callMonthFilter');
    if (monthFilter) monthFilter.addEventListener('change', refresh);

    if (typeFilter) typeFilter.addEventListener('change', refresh);
    if (searchInput && window.debounce) {
      searchInput.addEventListener('input', window.debounce(refresh, 500));
    } else if (searchInput) {
      searchInput.addEventListener('change', refresh);
    }

    if (btnExport) {
      btnExport.addEventListener('click', () => {
        this.exportCalls();
      });
    }
  }

  // Standard interface for main.js
  // Standard interface for main.js
  load() {
    const userFilter = document.getElementById('callUserFilter');
    const monthFilter = document.getElementById('callMonthFilter');
    const typeFilter = document.getElementById('callTypeFilter');
    const searchInput = document.getElementById('callSearchInput');

    if (userFilter) userFilter.value = 'all';
    if (monthFilter) monthFilter.value = '';
    if (typeFilter) typeFilter.value = 'all';
    if (searchInput) searchInput.value = '';

    this.loadCalls();
  }

  async loadUsersForFilter() {
    try {
      const resp = await auth.makeAuthenticatedRequest('/api/admin/users?per_page=100');
      if (!resp || !resp.ok) return;
      const data = await resp.json();
      const users = data.users || [];

      const select = document.getElementById('callUserFilter');
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

  async loadCalls(
    user_id = null,
    page = 1,
    per_page = 50,
    filter = "",
    date = "",
    search = "",
    call_type = ""
  ) {
    try {

      // ================================
      // Build base URL (admin or user)
      // ================================
      const container = document.getElementById("call-history-container");
      if (container) {
        container.innerHTML = '<div class="p-4 text-center text-gray-500">Loading...</div>';
      }

      // ================================
      // Build base URL (admin or user)
      // ================================
      let url = `/api/admin/all-call-history?page=${page}&per_page=${per_page}`;

      // ================================
      // Add filters dynamically
      // ================================
      if (user_id && user_id !== 'all') url += `&user_id=${user_id}`;
      if (filter) url += `&filter=${filter}`;          // today / week / month
      if (date) url += `&date=${date}`;                // custom date (YYYY-MM-DD)
      if (search) url += `&search=${encodeURIComponent(search)}`; // phone search
      if (call_type && call_type !== 'all') url += `&call_type=${call_type}`; // incoming/outgoing/missed

      // Month filter (UI driven)
      const monthFilter = document.getElementById('callMonthFilter');
      if (monthFilter && monthFilter.value) {
        url += `&month=${monthFilter.value}`;
      }

      // Make authenticated request
      const resp = await auth.makeAuthenticatedRequest(url);
      if (!resp) return;

      const data = await resp.json();

      if (!resp.ok) {
        auth.showNotification(data.error || 'Failed to load call history', 'error');
        return;
      }

      // Main list
      const list = data.call_history || [];

      if (!container) return;

      // ================================
      // Render Table
      // ================================
      if (list.length === 0) {
        container.innerHTML = `
          <div class="flex flex-col items-center justify-center py-12 bg-white rounded shadow">
            <div class="text-gray-400 mb-3">
              <i class="fas fa-search text-4xl"></i>
            </div>
            <h3 class="text-lg font-medium text-gray-900">No records found</h3>
            <p class="text-gray-500 text-sm mt-1">Try adjusting your search or filters</p>
          </div>
        `;
        // Clear pagination
        const pagination = document.getElementById("call-history-pagination");
        if (pagination) pagination.innerHTML = "";
        return;
      }

      container.innerHTML = `
        <div class="overflow-x-auto overflow-y-hidden bg-white rounded shadow">
          <table class="w-full mobile-card-table">
              <thead class="bg-gray-200">
            <tr>
              <th class="p-2 sm:p-3 text-left whitespace-nowrap">User</th>
              <th class="p-2 sm:p-3 text-left whitespace-nowrap">Number</th>
              <th class="p-2 sm:p-3 text-left whitespace-nowrap">Contact Name</th>
              <th class="p-2 sm:p-3 text-left whitespace-nowrap">Type</th>
              <th class="p-2 sm:p-3 text-left whitespace-nowrap">Duration</th>
              <th class="p-2 sm:p-3 text-left whitespace-nowrap">Recording</th>
              <th class="p-2 sm:p-3 text-left whitespace-nowrap">Timestamp</th>
            </tr>
          </thead>
          <tbody>
            ${list
          .map(
            (r) => {
              // Color badges for types
              let typeBadge = "";
              const cType = (r.call_type || "").toLowerCase();
              if (cType === "incoming") {
                typeBadge = `<span class="px-2 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-700">Incoming</span>`;
              } else if (cType === "outgoing") {
                typeBadge = `<span class="px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-700">Outgoing</span>`;
              } else if (cType === "missed") {
                typeBadge = `<span class="px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-700">Missed</span>`;
              } else {
                typeBadge = `<span class="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-700">${r.call_type}</span>`;
              }

              // Recording Player
              let recordingPlayer = '<span class="text-gray-400 text-xs">-</span>';
              if (r.recording_path) {
                let finalUrl = "";
                let rawPath = r.recording_path.trim();

                if (r.playback_url) {
                    finalUrl = r.playback_url;
                } else {
                    // Normalize backslashes to forward slashes
                    rawPath = rawPath.replace(/\\/g, '/');

                    // Remove leading slash if present to standardize
                    if (rawPath.startsWith('/')) {
                      rawPath = rawPath.substring(1);
                    }

                    // Remove "uploads/" prefix if present in the DB path (to avoid /uploads/uploads/...)
                    // The route is /uploads/..., which maps to static/uploads/...
                    if (rawPath.startsWith('uploads/')) {
                      rawPath = rawPath.substring(8); // Remove "uploads/"
                    }

                    // Construct clean URL
                    finalUrl = `/uploads/${rawPath}`;
                }

                // Calculate duration text (e.g., "00:30")
                const durationSec = parseInt(r.duration || 0, 10);
                const minutes = Math.floor(durationSec / 60);
                const seconds = durationSec % 60;
                const fmtDuration = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

                recordingPlayer = `
                  <div class="flex items-center space-x-2">
                    <audio controls class="h-8 w-28 hide-volume" preload="none">
                        <source src="${finalUrl}" type="${this.getAudioMimeType(rawPath)}">
                    </audio>
                    <span class="text-xs text-gray-500 font-medium">${fmtDuration}</span>
                  </div>
                  `;
              }

              return `
                <tr class="border-t hover:bg-gray-50 text-sm">
                  <td class="p-2 sm:p-3 align-top font-medium text-gray-900 whitespace-nowrap" data-label="User:">
                    ${r.user_name || r.user_id || '-'}
                  </td>
                  <td class="p-2 sm:p-3 align-top text-gray-600 whitespace-nowrap" data-label="Number:">${r.phone_number || '-'}</td>
                  <td class="p-2 sm:p-3 align-top text-gray-600" data-label="Contact:">
                    <div class="max-w-[150px] whitespace-normal break-words leading-tight">
                        ${r.contact_name || '-'}
                    </div>
                  </td>
                  <td class="p-2 sm:p-3 align-top" data-label="Type:">${typeBadge}</td>
                  <td class="p-2 sm:p-3 align-top text-gray-600" data-label="Duration:">${r.duration ? r.duration + "s" : "-"}</td>
                  <td class="p-2 sm:p-3 align-top min-w-[150px]" data-label="Recording:">${recordingPlayer}</td>
                  <td class="p-2 sm:p-3 align-top text-gray-600" data-label="Time:">
                    <div class="max-w-[120px] whitespace-normal break-words leading-tight">
                      ${window.formatDateTime(r.timestamp)}
                    </div>
                  </td>
                </tr>
                  `;
            }
          )
          .join("")
        }
          </tbody>
        </table>
      </div>
      `;

      // ================================
      // Render Pagination Buttons
      // ================================
      if (data.meta) {
        this.renderPagination(data.meta, user_id, filter, date, search, call_type);
      }
    }

    catch (e) {
      console.error(e);
      auth.showNotification("Failed to load call history", "error");
    }
  }

  // ======================================================
  // PAGINATION RENDERING
  // ======================================================
  renderPagination(meta, user_id, filter, date, search, call_type) {
    const pagination = document.getElementById("call-history-pagination");
    if (!pagination) return;

    pagination.innerHTML = `
      <div class="flex flex-col sm:flex-row justify-between items-center mt-4 p-4 gap-4">
        <button 
          class="px-4 py-2 bg-gray-300 rounded ${meta.has_prev ? "hover:bg-gray-400" : "opacity-50 cursor-not-allowed"}"
          ${meta.has_prev ? `onclick="callHistoryManager.loadCalls(${user_id ? `'${user_id}'` : 'null'}, ${meta.page - 1}, ${meta.per_page}, '${filter}', '${date}', '${search}', '${call_type}')"` : ""}
        >
          Previous
        </button>

        <span class="px-4 py-2">Page ${meta.page} of ${meta.pages}</span>

        <button 
          class="px-4 py-2 bg-gray-300 rounded ${meta.has_next ? "hover:bg-gray-400" : "opacity-50 cursor-not-allowed"}"
          ${meta.has_next ? `onclick="callHistoryManager.loadCalls(${user_id ? `'${user_id}'` : 'null'}, ${meta.page + 1}, ${meta.per_page}, '${filter}', '${date}', '${search}', '${call_type}')"` : ""}
        >
          Next
        </button>
      </div>
    `;
  }

  getAudioMimeType(path) {
    if (!path) return "audio/mpeg";
    const ext = path.split('.').pop().toLowerCase();
    const map = {
      'mp3': 'audio/mpeg',
      'wav': 'audio/wav',
      'ogg': 'audio/ogg',
      'm4a': 'audio/mp4',
      'aac': 'audio/aac',
      'opus': 'audio/opus',
      'webm': 'audio/webm',
      'amr': 'audio/amr',
      '3gp': 'audio/3gpp'
    };
    return map[ext] || "audio/mpeg";
  }

  async exportCalls() {
    const userFilter = document.getElementById('callUserFilter');
    const searchInput = document.getElementById('callSearchInput');
    const typeFilter = document.getElementById('callTypeFilter');
    const monthFilter = document.getElementById('callMonthFilter');

    const user_id = userFilter?.value === 'all' ? null : userFilter?.value;
    const search = searchInput?.value || "";
    const call_type = typeFilter?.value === 'all' ? "" : typeFilter?.value;
    const month = monthFilter?.value || "";

    try {
      let url = `/api/admin/all-call-history?per_page=10000`; // Fetch large number for export
      if (user_id) url += `&user_id=${user_id}`;
      if (search) url += `&search=${encodeURIComponent(search)}`;
      if (call_type) url += `&call_type=${call_type}`;
      if (month) url += `&month=${month}`;

      const resp = await auth.makeAuthenticatedRequest(url);
      if (!resp || !resp.ok) {
        auth.showNotification("Failed to fetch data for export", "error");
        return;
      }

      const data = await resp.json();
      const items = data.call_history || [];

      if (items.length === 0) {
        auth.showNotification("No records to export", "info");
        return;
      }

      // Initialize jsPDF
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF();

      // --- PDF Header ---
      const currentDate = new Date().toLocaleDateString();
      let userName = "All Users";
      if (userFilter) {
        const selectedOption = userFilter.options[userFilter.selectedIndex];
        if (selectedOption) {
          userName = selectedOption.text;
        }
      }

      // Title: nxtcall.app
      doc.setFontSize(18);
      doc.setTextColor(59, 130, 246); // Blue color like the logo
      const pageWidth = doc.internal.pageSize.getWidth();
      const text = "nxtcall.app";
      const textWidth = doc.getTextWidth(text);
      const textX = (pageWidth - textWidth) / 2;
      doc.text(text, textX, 20);

      // Report Info
      doc.setFontSize(11);
      doc.setTextColor(100);
      doc.text(`User Report: ${userName}`, 14, 30);
      doc.text(`Date: ${currentDate}`, 14, 36);

      // --- Table Data ---
      const tableHeaders = [["User", "Number", "Contact Name", "Type", "Duration", "Timestamp"]];
      const tableRows = items.map(r => [
        r.user_name || r.user_id || '-',
        r.phone_number || '-',
        (r.contact_name || '-'),
        r.call_type || '-',
        r.duration ? r.duration + "s" : "-",
        window.formatDateTime(r.timestamp)
      ]);

      doc.autoTable({
        head: tableHeaders,
        body: tableRows,
        startY: 45,
        theme: 'grid',
        headStyles: { fillColor: [59, 130, 246] }, // Blue header
        styles: { fontSize: 9 },
        margin: { top: 45 },
      });

      // Save PDF
      doc.save(`call_history_export_${new Date().toISOString().split('T')[0]}.pdf`);

    } catch (e) {
      console.error("Export failed", e);
      auth.showNotification("Export failed", "error");
    }
  }
}

