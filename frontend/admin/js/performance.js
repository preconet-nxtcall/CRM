/* admin/js/performance.js */

class PerformanceManager {

  constructor() {
    this.loadUsersForFilter();
  }

  // Standard interface for main.js
  load() {
    const sortSelect = document.getElementById("performanceSort");
    const userFilter = document.getElementById("performanceUserFilter");
    if (sortSelect) sortSelect.value = "desc";
    if (userFilter) userFilter.value = "all";

    this.loadPerformance("desc", "all", "all");
  }

  async loadUsersForFilter() {
    try {
      const resp = await auth.makeAuthenticatedRequest('/api/admin/users?per_page=100');
      if (!resp || !resp.ok) return;
      const data = await resp.json();
      const users = data.users || [];

      const select = document.getElementById('performanceUserFilter');
      if (!select) return;

      // Keep "All Users" option
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

  async loadPerformance(sortType = "desc", dateFilter = "all", userId = "all") {
    try {
      let url = `/api/admin/performance?sort=${sortType}&filter=${dateFilter}`;
      if (userId && userId !== 'all') {
        url += `&user_id=${userId}`;
      }

      const resp = await auth.makeAuthenticatedRequest(url);
      if (!resp) return;

      const data = await resp.json();

      if (!resp.ok) {
        auth.showNotification(data.error || "Failed to load performance", "error");
        return;
      }

      const labels = data.labels || [];
      const values = data.values || [];
      const user_ids = data.user_ids || [];
      const statuses = data.statuses || [];
      const details = data.details || [];

      // Store stats for modal access
      this.userStats = {};
      user_ids.forEach((uid, i) => {
        this.userStats[uid] = {
          score: values[i],
          status: statuses[i],
          details: details[i]
        };
      });

      // Render both chart + table
      this.renderChart(labels, values);
      this.renderTable(labels, values, user_ids, statuses);

    } catch (error) {
      console.error(error);
      auth.showNotification(`Error: ${error.message}`, 'error');
    }
  }

  renderChart(labels, values) {
    const canvas = document.getElementById("performanceBarCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    // Robustly destroy existing chart
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }

    // Double check canvas for attached instance (Chart.js 3+)
    const existingChart = Chart.getChart(canvas);
    if (existingChart) {
      existingChart.destroy();
    }

    const dataLabelPlugin = {
      id: 'dataLabelPlugin',
      afterDatasetsDraw(chart, args, options) {
        const { ctx } = chart;
        chart.data.datasets.forEach((dataset, i) => {
          const meta = chart.getDatasetMeta(i);
          meta.data.forEach((bar, index) => {
            const value = dataset.data[index];
            if (value > 0) {
              ctx.fillStyle = '#000000';
              ctx.font = 'bold 12px Inter';
              ctx.textAlign = 'center';
              ctx.fillText(`${value}%`, bar.x, bar.y - 5);
            }
          });
        });
      }
    };

    const colors = [
      '#3B82F6', '#10B981', '#EF4444', '#8B5CF6',
      '#F59E0B', '#06B6D4', '#EC4899', '#6366F1',
    ];

    this.chart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Activity Ratio (%)",
            data: values,
            backgroundColor: labels.map((_, i) => colors[i % colors.length]),
            borderRadius: 4,
            barPercentage: 0.6,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => `Ratio: ${ctx.raw}%`
            }
          }
        },
        scales: {
          y: { beginAtZero: true, max: 100, grid: { display: false } },
          x: { grid: { display: false } }
        }
      },
      plugins: [dataLabelPlugin]
    });
  }

  renderTable(labels, values, ids, statuses) {
    const body = document.getElementById("performanceTableBody");
    if (!body) return;

    // Update Header if needed? 
    // Assuming table header has: Rank, Team Member, Score, Details
    // We should probably inject a Status column or combine it.
    // For now, I'll put Status in a pill next to Score or in a new column if I could edit HTML easily.
    // I will combine Score and Status in the same cell for layout stability.

    if (labels.length === 0) {
      body.innerHTML = `<tr><td colspan="5" class="p-6 text-center text-gray-500">No performance data found</td></tr>`;
      return;
    }

    body.innerHTML = labels.map((name, i) => {
      const score = values[i];
      const status = statuses[i] || 'Unknown';
      let statusColor = 'bg-gray-100 text-gray-800';
      if (status === 'Excellent') statusColor = 'bg-green-100 text-green-800';
      else if (status === 'Moderate') statusColor = 'bg-yellow-100 text-yellow-800';
      else if (status === 'Poor' || status === 'Inactive') statusColor = 'bg-red-100 text-red-800';

      return `
      <tr class="border-t hover:bg-gray-50 transition-colors">
        <td class="px-4 py-3 sm:px-6 sm:py-4 text-gray-900 font-medium" data-label="Rank:">#${i + 1}</td>
        <td class="px-4 py-3 sm:px-6 sm:py-4 text-gray-700 font-medium min-w-[120px]" data-label="User:">${name}</td>
        <td class="px-4 py-3 sm:px-6 sm:py-4" data-label="Performance:">
             <div class="flex flex-col gap-1">
                <span class="text-sm font-bold text-gray-900">${score}% Efficiency</span>
                <span class="inline-flex w-fit items-center px-2 py-0.5 rounded text-xs font-medium ${statusColor}">
                    ${status}
                </span>
             </div>
        </td>
        <td class="px-4 py-3 sm:px-6 sm:py-4" data-label="Actions:">
          <button 
            class="text-blue-600 hover:text-blue-900 font-medium text-sm transition-colors"
            onclick="performanceManager.viewUserCallHistory(${ids[i]}, '${name.replace(/'/g, "\\'")}')"
          >
            View Details
          </button>
        </td>
      </tr>
    `}).join('');
  }

  async viewUserCallHistory(userId, userName, page = 1) {
    try {
      const modal = document.getElementById('userCallHistoryModal');
      const title = document.getElementById('modalUserTitle');

      if (!modal) return;
      if (title) title.textContent = userName;

      this.currentModalUser = { userId, userName };
      this.currentModalFilter = "all";

      // Render the Shell
      this.renderModalShell(userName);

      // Load initial data
      await this.loadModalData(userId, userName, 1);

    } catch (e) {
      console.error("Error viewing user call history", e);
      auth.showNotification(`Error opening details: ${e.message}`, "error");
    }
  }

  // New method to render the static parts of the modal
  renderModalShell(userName) {
    const modal = document.getElementById('userCallHistoryModal');
    const title = document.getElementById('modalUserTitle');
    if (!modal) return;
    if (title) title.textContent = userName;

    modal.querySelector('.modal-content').innerHTML = `
        <!-- Top Header: Name & Stats -->
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center pb-4 border-b border-gray-200 p-4 sm:p-6">
          <h3 id="modalUserTitle" class="text-xl font-bold text-gray-900 mb-4 md:mb-0">${userName}</h3>
          
          <!-- Stats Row -->
          <div id="modalUserStats" class="flex flex-wrap gap-4 md:gap-8 bg-gray-50 px-4 py-2 rounded-lg">
             <!-- Populated later -->
          </div>
          
          <button type="button" class="text-gray-400 hover:text-gray-500 absolute top-4 right-4" onclick="document.getElementById('userCallHistoryModal').classList.add('hidden');">
            <span class="sr-only">Close modal</span>
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
          </button>
        </div>

        <div class="p-4 sm:p-6">
            <!-- Controls: Filters & Download -->
            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
              <!-- Filter Buttons -->
              <div class="flex bg-gray-100 p-1 rounded-lg">
                <button onclick="performanceManager.changeModalFilter('all')" class="modal-filter-btn px-4 py-1.5 rounded-md text-sm font-medium transition-all">All</button>
                <button onclick="performanceManager.changeModalFilter('today')" class="modal-filter-btn px-4 py-1.5 rounded-md text-sm font-medium transition-all">Today</button>
                <button onclick="performanceManager.changeModalFilter('month')" class="modal-filter-btn px-4 py-1.5 rounded-md text-sm font-medium transition-all">Month</button>
              </div>

              <!-- Download Report Button -->
              <button onclick="performanceManager.downloadModalReport()" class="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 text-sm font-medium transition-colors shadow-sm">
                <i class="fas fa-file-pdf"></i>
                Download Report
              </button>
            </div>

            <!-- Table -->
            <div class="overflow-hidden overflow-y-auto max-h-[50vh] border border-gray-200 rounded-lg">
                <table class="min-w-full divide-y divide-gray-200">
                  <thead class="bg-gray-50 sticky top-0 z-10">
                    <tr>
                      <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider bg-gray-50">Type</th>
                      <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider bg-gray-50">Number</th>
                      <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider bg-gray-50">Duration</th>
                      <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider bg-gray-50">Date & Time</th>
                    </tr>
                  </thead>
                  <tbody id="modalCallHistoryBody" class="bg-white divide-y divide-gray-200">
                    <!-- Populated by JS -->
                  </tbody>
                </table>
            </div>

            <!-- Pagination -->
            <div id="modalCallHistoryPagination" class="mt-4"></div>
        </div>
      `;

    this.updateFilterButtons();
    modal.classList.remove('hidden');
  }

  updateFilterButtons() {
    const btns = document.querySelectorAll('.modal-filter-btn');
    const filters = ['all', 'today', 'month'];
    btns.forEach((btn, i) => {
      if (filters[i] === this.currentModalFilter) {
        btn.classList.add('bg-white', 'text-gray-900', 'shadow-sm');
        btn.classList.remove('text-gray-500', 'hover:text-gray-900');
      } else {
        btn.classList.remove('bg-white', 'text-gray-900', 'shadow-sm');
        btn.classList.add('text-gray-500', 'hover:text-gray-900');
      }
    });
  }

  changeModalFilter(type) {
    this.currentModalFilter = type;
    this.updateFilterButtons();
    this.loadModalData(this.currentModalUser.userId, this.currentModalUser.userName, 1);
  }

  changePage(page) {
    this.loadModalData(this.currentModalUser.userId, this.currentModalUser.userName, page);
  }

  async loadModalData(userId, userName, page = 1) {
    const tbody = document.getElementById('modalCallHistoryBody');
    const paginationContainer = document.getElementById('modalCallHistoryPagination');

    let url = `/api/admin/all-call-history?user_id=${userId}&page=${page}&per_page=30`;

    if (this.currentModalFilter && this.currentModalFilter !== 'all') {
      url += `&filter=${this.currentModalFilter}`;
    }

    const resp = await auth.makeAuthenticatedRequest(url);
    if (!resp || !resp.ok) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-4 text-center text-red-500 text-sm">Failed to load history</td></tr>';
      return;
    }

    const data = await resp.json();
    const calls = data.call_history || [];
    const meta = data.meta || {};
    const stats = data.stats || null;

    const statsContainer = document.getElementById('modalUserStats');
    if (statsContainer) {
      if (stats) {
        const d = stats.details || {};
        statsContainer.innerHTML = `
                <div>
                    <p class="text-[10px] text-gray-500 uppercase mb-0.5">Check In</p>
                    <p class="font-bold text-sm text-gray-900">
                      ${d.check_in ? new Date(d.check_in).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-'}
                    </p>
                </div>
                <div>
                    <p class="text-[10px] text-gray-500 uppercase mb-0.5">Check Out</p>
                    <p class="font-bold text-sm text-gray-900">
                      ${d.check_out ? new Date(d.check_out).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-'}
                    </p>
                </div>
                 <div>
                    <p class="text-[10px] text-gray-500 uppercase mb-0.5">Work Time</p>
                    <p class="font-bold text-sm text-gray-900">${d.work_time || '0s'}</p>
                </div>
                 <div>
                    <p class="text-[10px] text-gray-500 uppercase mb-0.5">Active</p>
                    <p class="font-bold text-sm text-green-600">${d.active_time || '0s'}</p>
                </div>
                 <div>
                    <p class="text-[10px] text-gray-500 uppercase mb-0.5">Inactive</p>
                    <p class="font-bold text-sm text-red-600">${d.inactive_time || '0s'}</p>
                </div>
              `;
      } else {
        // Clear stats if not provided (e.g. filtered to a day with no attendance)
        statsContainer.innerHTML = `
                <div><p class="text-[10px] text-gray-500 uppercase mb-0.5">Check In</p><p class="font-bold text-sm text-gray-900">-</p></div>
                <div><p class="text-[10px] text-gray-500 uppercase mb-0.5">Check Out</p><p class="font-bold text-sm text-gray-900">-</p></div>
                <div><p class="text-[10px] text-gray-500 uppercase mb-0.5">Work Time</p><p class="font-bold text-sm text-gray-900">0s</p></div>
                <div><p class="text-[10px] text-gray-500 uppercase mb-0.5">Active</p><p class="font-bold text-sm text-green-600">0s</p></div>
                <div><p class="text-[10px] text-gray-500 uppercase mb-0.5">Inactive</p><p class="font-bold text-sm text-red-600">0s</p></div>
         `;
      }
    }

    if (calls.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-4 text-center text-gray-500 text-sm">No call records found</td></tr>';
      if (paginationContainer) paginationContainer.innerHTML = '';
      return;
    }

    tbody.innerHTML = calls.map(call => `
      <tr>
        <td class="px-4 py-2 whitespace-nowrap">
          <span class="px-2 inline-flex text-[10px] leading-4 font-semibold rounded-full 
            ${call.call_type === 'incoming' ? 'bg-green-100 text-green-800' :
        call.call_type === 'outgoing' ? 'bg-blue-100 text-blue-800' :
          'bg-red-100 text-red-800'}">
            ${call.call_type}
          </span>
        </td>
        <td class="px-4 py-2 whitespace-nowrap text-sm font-medium text-gray-900">
          ${call.number || call.phone_number}
        </td>
        <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-500">
           ${this.formatDuration(call.duration)}
        </td>
        <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-500">
          ${new Date(call.timestamp).toLocaleString(undefined, {
            month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
          })}
        </td>
      </tr>
    `).join('');

    this.renderModalPagination(meta, paginationContainer);
  }

  async downloadModalReport() {
    try {
      const userId = this.currentModalUser?.userId;
      if (!userId) return;

      const filter = this.currentModalFilter || 'all';
      // auth.showNotification("Generating Report...", "info");

      const token = auth.getToken();
      const response = await fetch(`/api/admin/download-user-history?user_id=${userId}&filter=${filter}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) throw new Error("Failed to download");

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `CallHistory_Report_${filter}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      auth.showNotification("Report downloaded successfully", "success");

    } catch (e) {
      console.error(e);
      auth.showNotification("Failed to download report", "error");
    }
  }

  renderModalPagination(meta, container) {
    if (!container || !meta || meta.pages <= 1) {
      if (container) container.innerHTML = '';
      return;
    }

    const currentPage = meta.page;
    const totalPages = meta.pages;

    let pagesHtml = '';

    // Show max 5 page numbers
    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, currentPage + 2);

    for (let i = startPage; i <= endPage; i++) {
      pagesHtml += `
        <button 
          onclick="performanceManager.changePage(${i})"
          class="px-3 py-1 rounded ${i === currentPage ? 'bg-blue-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'} border border-gray-300 text-sm font-medium">
          ${i}
        </button>
      `;
    }

    container.innerHTML = `
      <div class="flex items-center justify-between px-4 py-3 bg-gray-50 border-t border-gray-200">
        <div class="text-sm text-gray-700">
          Showing page <span class="font-medium">${currentPage}</span> of <span class="font-medium">${totalPages}</span>
          <span class="text-gray-500">(${meta.total} total records)</span>
        </div>
        <div class="flex gap-1">
          <button 
            onclick="performanceManager.changePage(${currentPage - 1})"
            ${!meta.has_prev ? 'disabled' : ''}
            class="px-3 py-1 rounded bg-white text-gray-700 hover:bg-gray-50 border border-gray-300 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed">
            Previous
          </button>
          ${pagesHtml}
          <button 
            onclick="performanceManager.changePage(${currentPage + 1})"
            ${!meta.has_next ? 'disabled' : ''}
            class="px-3 py-1 rounded bg-white text-gray-700 hover:bg-gray-50 border border-gray-300 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed">
            Next
          </button>
        </div>
      </div>
    `;
  }

  formatDuration(seconds) {
    if (seconds === undefined || seconds === null) return "0s";
    const sec = parseInt(seconds, 10);
    if (isNaN(sec) || sec === 0) return "0s";

    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;

    const parts = [];
    if (h > 0) parts.push(`${h}h`);
    if (m > 0) parts.push(`${m}m`);
    if (s > 0 || parts.length === 0) parts.push(`${s}s`);
    return parts.join(' ');
  }
}


