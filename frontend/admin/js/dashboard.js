/* admin/js/dashboard.js - Neodove Redesign */

class DashboardManager {
  constructor() {
    this.stats = {};
    this.analytics = {};
    this.performanceChart = null;
    this.sourceChart = null;
  }

  async loadStats() {
    try {
      await Promise.all([
        this.fetchGeneralStats(),
        this.fetchLeadAnalytics(),
        this.fetchRecentActivity()
      ]);

      this.updateProfile();
      this.renderKPICards();
      this.renderPipelineBar();
      this.renderAgentTable();
      this.renderSourceChart();
      this.renderCallChart();

    } catch (e) {
      console.error("Dashboard Load Error:", e);
      // Optional: visual error feedback in UI
    }
  }

  async fetchGeneralStats() {
    const url = `/api/admin/dashboard-stats?timezone_offset=${new Date().getTimezoneOffset()}`;
    const resp = await auth.makeAuthenticatedRequest(url);
    if (resp && resp.ok) {
      const data = await resp.json();
      this.stats = data.stats || {};
    }
  }

  async fetchLeadAnalytics() {
    const resp = await auth.makeAuthenticatedRequest('/api/admin/analytics/leads');
    if (resp && resp.ok) {
      this.analytics = await resp.json();
    }
  }

  async fetchRecentActivity() {
    // Reuse existing endpoint for online/offline status as "Activity"
    // In a real scenario, this would be a dedicated activity log endpoint
    const resp = await auth.makeAuthenticatedRequest('/api/admin/recent-sync');
    if (resp && resp.ok) {
      const data = await resp.json();
      this.renderActivityFeed(data.recent_sync || []);
    }
  }

  updateProfile() {
    if (this.stats.admin_name) {
      document.getElementById('sidebar-admin-name').textContent = this.stats.admin_name;
    }
    if (this.stats.admin_email) {
      document.getElementById('sidebar-admin-email').textContent = this.stats.admin_email;
    }
  }

  /* ------------------------------------------------
     1. KPI Cards
  ------------------------------------------------ */
  renderKPICards() {
    const container = document.getElementById('stats-cards');
    if (!container) return;

    // Calculate Call Count (Today) from chart data if possible, or use total calls
    // Since API gives "call_trend", the last item is today
    let callsToday = 0;
    if (this.stats.call_trend && this.stats.call_trend.data) {
      const dataArr = this.stats.call_trend.data;
      callsToday = dataArr[dataArr.length - 1] || 0;
    }

    const cards = [
      { title: "Total Leads", value: this.analytics.total_leads || 0, icon: "database", color: "blue" },
      { title: "Calls Today", value: callsToday, icon: "phone", color: "green" },
      { title: "Missed Calls", value: this.stats.missed_calls_today || 0, icon: "phone-slash", color: "red" },
      { title: "Conversion Rate", value: (this.analytics.conversion_rate || 0) + '%', icon: "chart-line", color: "purple" }
    ];

    container.innerHTML = cards.map(c => `
             <div class="dashboard-card p-6 flex items-start justify-between">
                <div>
                    <h4 class="kpi-label mb-1">${c.title}</h4>
                    <span class="kpi-value text-gray-900">${c.value}</span>
                </div>
                <div class="w-10 h-10 rounded-full bg-${c.color}-50 flex items-center justify-center text-${c.color}-600">
                    <i class="fas fa-${c.icon}"></i>
                </div>
            </div>
        `).join('');
  }

  /* ------------------------------------------------
     2. Pipeline Bar
  ------------------------------------------------ */
  renderPipelineBar() {
    const container = document.getElementById('pipeline-bar');
    if (!container) return;

    const statusMap = this.analytics.by_status || {};

    // Define logical pipeline order
    const order = [
      { key: 'New', label: 'New Leads', class: 'seg-new' },
      { key: 'Attempted', label: 'Attempted', class: 'seg-attempted' },
      { key: 'Connected', label: 'Connected', class: 'seg-connected' },
      { key: 'Interested', label: 'Interested', class: 'seg-interested' },
      { key: 'Follow Up', label: 'Follow Up', class: 'seg-followup' }, // Note: check DB key carefully
      { key: 'Closed', label: 'Closed', class: 'seg-closed' },
    ];

    // Normalization helper for insensitive match if needed
    const getCount = (key) => {
      // Check direct match
      if (statusMap[key] !== undefined) return statusMap[key];
      // Check lowercase/alternates
      for (let k in statusMap) {
        if (k.toLowerCase() === key.toLowerCase()) return statusMap[k];
        if (key === 'Follow Up' && (k === 'FollowUp' || k === 'Follow-Up')) return statusMap[k];
      }
      return 0;
    };

    container.innerHTML = order.map(stage => {
      const count = getCount(stage.key);
      return `
                <div class="pipeline-segment ${stage.class}">
                    <span class="pipeline-count">${count}</span>
                    <span class="pipeline-label">${stage.label}</span>
                </div>
            `;
    }).join('');
  }

  /* ------------------------------------------------
     3. Agent Performance Table
  ------------------------------------------------ */
  renderAgentTable() {
    const tbody = document.getElementById('agent-performance-body');
    if (!tbody) return;

    const agents = this.analytics.agent_performance || [];

    if (agents.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" class="text-center py-4 text-gray-400">No agent data available</td></tr>`;
      return;
    }

    tbody.innerHTML = agents.map(agent => `
            <tr>
                <td>
                    <div class="flex items-center gap-2">
                        <div class="w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold">
                            ${agent.name.charAt(0).toUpperCase()}
                        </div>
                        <span class="font-medium text-gray-800">${agent.name}</span>
                    </div>
                </td>
                <td class="text-right font-medium">${agent.assigned}</td>
                <td class="text-right text-gray-600">${agent.converted}</td>
                <td class="text-right">
                    <span class="bg-green-50 text-green-700 px-2 py-1 rounded text-xs font-semibold">
                        ${agent.conversion_rate}%
                    </span>
                </td>
            </tr>
        `).join('');
  }

  /* ------------------------------------------------
     4. Call Analytics Chart (Bar)
  ------------------------------------------------ */
  renderCallChart() {
    const ctx = document.getElementById('performanceChart');
    if (!ctx) return;

    if (this.performanceChart) this.performanceChart.destroy();

    const trend = this.stats.call_trend || {};
    const labels = trend.labels || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const data = trend.data || [0, 0, 0, 0, 0, 0, 0];

    // Create a gradient for the bar
    const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, '#2563EB'); // Blue 600
    gradient.addColorStop(1, '#93C5FD'); // Blue 300

    this.performanceChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Total Calls',
          data: data,
          backgroundColor: '#2563EB',
          borderRadius: 4,
          barThickness: 20
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          y: {
            beginAtZero: true,
            grid: {
              color: '#F3F4F6',
              borderDash: [2, 4]
            },
            ticks: { font: { size: 10 } }
          },
          x: {
            grid: { display: false },
            ticks: { font: { size: 10 } }
          }
        }
      }
    });
  }

  /* ------------------------------------------------
     5. Lead Source Chart (Donut)
  ------------------------------------------------ */
  renderSourceChart() {
    const ctx = document.getElementById('sourceChart');
    const legendContainer = document.getElementById('source-legend');
    if (!ctx) return;

    if (this.sourceChart) this.sourceChart.destroy();

    const sources = this.analytics.by_source || {};
    const labels = Object.keys(sources);
    const data = Object.values(sources);

    // Neodove/Modern SaaS Palette
    const colors = ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#6B7280'];

    this.sourceChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: data,
          backgroundColor: colors,
          borderWidth: 0,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '75%',
        plugins: {
          legend: { display: false }
        }
      }
    });

    // Custom Legend
    if (legendContainer && labels.length > 0) {
      legendContainer.innerHTML = labels.map((label, i) => `
                <div class="flex items-center justify-between text-sm">
                    <div class="flex items-center gap-2">
                        <span class="w-3 h-3 rounded-full" style="background-color: ${colors[i % colors.length]}"></span>
                        <span class="text-gray-600">${label}</span>
                    </div>
                    <span class="font-bold text-gray-800">${data[i]}</span>
                </div>
            `).join('');
    } else if (legendContainer) {
      legendContainer.innerHTML = '<div class="text-center text-xs text-gray-400">No source data</div>';
    }
  }

  /* ------------------------------------------------
     6. Activity Feed
  ------------------------------------------------ */
  renderActivityFeed(activities) {
    const container = document.getElementById('activity-feed');
    if (!container) return;

    if (activities.length === 0) return; // Keep default empty msg

    // Helper to check today
    const isOnlineToday = (isoDate) => {
      if (!isoDate) return false;
      const d = new Date(isoDate);
      const now = new Date();
      return d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
    };

    container.innerHTML = activities.slice(0, 5).map(act => {
      const isOnline = isOnlineToday(act.last_sync);
      // Mocking "Action" text based on status because we don't have event logs yet
      // If user syncs, it means they are active/app usage
      const actionText = isOnline ? "Active on App" : "Last Sync";
      const timeText = window.formatDateTime(act.last_sync);

      return `
                <div class="activity-item">
                    <div class="activity-icon ${isOnline ? 'bg-blue-50 text-blue-600' : 'bg-gray-50 text-gray-400'}">
                        <i class="fas fa-${isOnline ? 'mobile-alt' : 'clock'}"></i>
                    </div>
                    <div class="activity-content">
                        <p class="activity-title">
                            <span class="font-semibold">${act.name}</span>
                            <span class="font-normal text-gray-500">${actionText}</span>
                        </p>
                        <p class="activity-time">${timeText}</p>
                    </div>
                </div>
            `;
    }).join('');
  }
}
