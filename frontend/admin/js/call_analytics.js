class CallAnalyticsManager {

  constructor() {
    this.data = null;
    this.currentPeriod = 'all'; // Default to all as requested
  }

  async loadAnalytics() {
    try {
      const resp = await auth.makeAuthenticatedRequest(
        `/api/admin/call-analytics?period=${this.currentPeriod}`
      );

      if (!resp.ok) {
        auth.showNotification("Failed to load analytics", "error");
        return;
      }

      const data = await resp.json();
      this.data = data;

      this.updateKPICards();
      // Charts removed as per request
      // this.renderCharts();

      // Ensure user_summary is populated from the main response
      if (this.data.user_summary) {
        this.renderTable();
      } else {
        // Fallback if structure is different
        this.renderTable();
      }

      this.updateFilterUI();

    } catch (e) {
      console.error(e);
      auth.showNotification("Analytics error", "error");
    }
  }

  updateFilterUI() {
    // Improve button styles
    const btnAll = document.getElementById('perf-filter-all');
    const btnToday = document.getElementById('perf-filter-today');
    const btnMonth = document.getElementById('perf-filter-month');

    // Helper to reset classes
    const setInactive = (btn) => {
      if (!btn) return;
      btn.classList.remove('bg-gray-100', 'text-gray-900', 'active');
      btn.classList.add('text-gray-500');
    };

    const setActive = (btn) => {
      if (!btn) return;
      btn.classList.add('bg-gray-100', 'text-gray-900', 'active');
      btn.classList.remove('text-gray-500');
    };

    if (btnAll && btnToday && btnMonth) {
      // Reset all
      setInactive(btnAll);
      setInactive(btnToday);
      setInactive(btnMonth);

      // Activate current
      if (this.currentPeriod === 'all') setActive(btnAll);
      else if (this.currentPeriod === 'today') setActive(btnToday);
      else if (this.currentPeriod === 'month') setActive(btnMonth);
    }
  }

  updateKPICards() {
    if (!this.data) return;

    // API returns flat structure
    const kpis = this.data;

    // Helper to safely set text content
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };

    setText("analytics-total-calls", (kpis.total_calls || 0).toLocaleString());
    setText("analytics-total-duration", this.formatDuration(kpis.total_duration || 0));
    setText("analytics-total-answered", (kpis.total_answered || 0).toLocaleString());

    // Calculate latest sync from user summary if available
    let latestSync = null;
    if (this.data.user_summary && Array.isArray(this.data.user_summary)) {
      const syncs = this.data.user_summary
        .map(u => u.last_sync ? new Date(u.last_sync) : null)
        .filter(d => d !== null);
      if (syncs.length > 0) {
        latestSync = new Date(Math.max.apply(null, syncs));
      }
    }

    if (latestSync) {
      setText("analytics-last-sync", latestSync.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true }));
    } else {
      setText("analytics-last-sync", "Never");
    }

    setText("analytics-outbound", (kpis.outgoing || 0).toLocaleString());
    setText("analytics-inbound", (kpis.incoming || 0).toLocaleString());
    setText("analytics-avg-outbound", this.formatDuration(kpis.avg_outbound_duration || 0));
    setText("analytics-avg-inbound", this.formatDuration(kpis.avg_inbound_duration || 0));
  }

  renderTable() {
    const container = document.getElementById("call-analytics-table-container");
    if (!container) return;

    const rows = this.data?.user_summary || [];

    container.innerHTML = `
      <div class="bg-white overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full mobile-card-table">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider whitespace-nowrap">User</th>
                <th class="px-6 py-3 text-center text-xs font-bold text-gray-500 uppercase tracking-wider whitespace-nowrap">Incoming</th>
                <th class="px-6 py-3 text-center text-xs font-bold text-gray-500 uppercase tracking-wider whitespace-nowrap">Outgoing</th>
                <th class="px-6 py-3 text-center text-xs font-bold text-gray-500 uppercase tracking-wider whitespace-nowrap">Missed</th>
                <th class="px-6 py-3 text-center text-xs font-bold text-gray-500 uppercase tracking-wider whitespace-nowrap">Rejected</th>
                <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider whitespace-nowrap">Total Duration</th>
                <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider whitespace-nowrap">Last Sync</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              ${rows.length
        ? rows.map(row => `
                    <tr class="hover:bg-gray-50 transition-colors">
                      <td class="p-3 px-6 text-sm font-medium text-gray-900 whitespace-nowrap" data-label="User">${row.name || row.user_name || "-"}</td>
                      <td class="p-3 text-sm text-center" data-label="Incoming">
                        <span class="inline-block px-2 py-1 rounded bg-green-100 text-green-800 font-medium min-w-[30px]">
                          ${row.incoming || 0}
                        </span>
                      </td>
                      <td class="p-3 text-sm text-center" data-label="Outgoing">
                        <span class="inline-block px-2 py-1 rounded bg-purple-100 text-purple-800 font-medium min-w-[30px]">
                          ${row.outgoing || 0}
                        </span>
                      </td>
                      <td class="p-3 text-sm text-center" data-label="Missed">
                        <span class="inline-block px-2 py-1 rounded bg-red-100 text-red-800 font-medium min-w-[30px]">
                          ${row.missed || 0}
                        </span>
                      </td>
                      <td class="p-3 text-sm text-center" data-label="Rejected">
                        <span class="inline-block px-2 py-1 rounded bg-orange-100 text-orange-800 font-medium min-w-[30px]">
                          ${row.rejected || 0}
                        </span>
                      </td>
                      <td class="p-3 px-6 text-sm text-gray-600 whitespace-nowrap" data-label="Total Duration">
                        ${this.formatDuration(row.total_duration_seconds || 0)}
                      </td>
                      <td class="p-3 px-6 text-sm text-gray-500 whitespace-nowrap" data-label="Last Sync">
                        ${row.last_sync ? new Date(row.last_sync).toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true }) : 'Never'}
                      </td>
                    </tr>
                  `).join("")
        : `
                    <tr>
                      <td colspan="7" class="p-6 text-center text-gray-500">
                        <i class="fas fa-filter text-3xl mb-2 text-gray-300"></i>
                        <div>No user data available for this period</div>
                      </td>
                    </tr>
                  `
      }
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  formatDuration(seconds) {
    if (!seconds || seconds === 0) return "0s";

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    const parts = [];
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);

    return parts.join(" ");
  }

  setPeriod(period) {
    if (this.currentPeriod === period) return;
    this.currentPeriod = period;
    this.loadAnalytics(); // Reload data
  }

  async downloadReport() {
    try {
      const token = auth.getToken();
      // Use fetch with blob to handle file download properly with auth headers if needed, 
      // or simple window.open if using cookie auth, but here we likely need the JWT header.
      // Since window.open doesn't support custom headers easily, we'll use fetch + blob.

      // auth.showNotification("Generating PDF Report...", "info");

      const response = await fetch(`/api/admin/call-analytics/download-report?period=${this.currentPeriod}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error("Failed to generate report");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      // Filename is usually in Content-Disposition header, but we can set a default
      a.download = `NxtCall_Report_${this.currentPeriod}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      auth.showNotification("Report downloaded successfully", "success");

    } catch (e) {
      console.error(e);
      auth.showNotification("Failed to download report", "error");
    }
  }

  init() {
    this.loadAnalytics();

    // Bind Events
    const btnAll = document.getElementById('perf-filter-all');
    const btnToday = document.getElementById('perf-filter-today');
    const btnMonth = document.getElementById('perf-filter-month');
    const btnDownload = document.getElementById('btnDownloadReport');

    if (btnAll) {
      btnAll.addEventListener('click', () => this.setPeriod('all'));
    }
    if (btnToday) {
      btnToday.addEventListener('click', () => this.setPeriod('today'));
    }
    if (btnMonth) {
      btnMonth.addEventListener('click', () => this.setPeriod('month'));
    }
    if (btnDownload) {
      btnDownload.addEventListener('click', () => this.downloadReport());
    }

    // Auto-refresh every 60 seconds
    setInterval(() => this.loadAnalytics(), 60000);
  }
}

// Initialize the manager
