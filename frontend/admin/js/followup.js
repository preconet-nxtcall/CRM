/* admin/js/followup.js */

class FollowupManager {
    constructor() {
        this.followups = [];
        this.meta = {};
        this.page = 1;
        this.perPage = 30;

        this.tbody = document.getElementById('followupsTableBody');
        this.emptyState = document.getElementById('followupsEmptyState');
        this.paginationContainer = document.getElementById('followupsPagination');

        this.userFilter = document.getElementById('followupUserFilter');
        this.dateFilters = document.querySelectorAll('.followup-date-filter');
        this.currentFilter = 'all';
        this.currentUserId = 'all';

        this.initFilters();
    }

    initFilters() {
        // User Filter Change
        if (this.userFilter) {
            this.userFilter.addEventListener('change', (e) => {
                this.currentUserId = e.target.value;
                this.load();
            });
        }

        // Date Filter Clicks
        this.dateFilters.forEach(btn => {
            btn.addEventListener('click', () => {
                // Update active state
                this.dateFilters.forEach(b => {
                    b.classList.remove('bg-gray-100', 'active', 'text-gray-900', 'font-semibold');
                    b.classList.add('text-gray-700', 'hover:bg-gray-50'); // Default inactive
                });

                // Active style
                btn.classList.remove('text-gray-700', 'hover:bg-gray-50');
                btn.classList.add('bg-gray-100', 'active', 'text-gray-900', 'font-semibold');

                this.currentFilter = btn.dataset.filter;
                this.load();
            });
        });
    }

    // Called by main.js when the section is activated
    async load() {
        this.page = 1; // Reset to first page on reload/filter change
        // Load users only once if empty
        if (this.userFilter && this.userFilter.options.length <= 1) {
            await this.loadUsers();
        }
        await this.fetchFollowups();
        this.render();
    }

    async loadUsers() {
        try {
            console.log('Fetching users for filter...');
            // Request large page size to get all users for the dropdown
            const response = await auth.makeAuthenticatedRequest('/api/admin/users?per_page=1000');
            if (response && response.ok) {
                const data = await response.json();
                console.log('Users fetched:', data);
                const users = data.users || [];

                // Clear existing (except "All")
                while (this.userFilter.options.length > 1) {
                    this.userFilter.remove(1);
                }

                if (users.length === 0) {
                    console.warn('No users returned from API');
                }

                users.forEach(user => {
                    const option = document.createElement('option');
                    option.value = user.id;
                    option.textContent = user.name || user.email || `User ${user.id}`;
                    this.userFilter.appendChild(option);
                });

                // Restore selection if reloaded
                this.userFilter.value = this.currentUserId;
            } else {
                console.error('Failed to fetch users response not OK');
            }
        } catch (error) {
            console.error('Failed to load users for filter', error);
        }
    }

    async fetchFollowups() {
        try {
            const params = new URLSearchParams();
            if (this.currentUserId !== 'all') params.append('user_id', this.currentUserId);
            if (this.currentFilter !== 'all') params.append('filter', this.currentFilter);

            // Pagination
            params.append('page', this.page);
            params.append('per_page', this.perPage);

            const url = `/api/admin/followups?${params.toString()}`;
            const response = await auth.makeAuthenticatedRequest(url);

            if (response && response.ok) {
                const data = await response.json();
                if (data.followups) {
                    this.followups = data.followups;
                    this.meta = data.meta;
                } else {
                    // Fallback for legacy format
                    this.followups = Array.isArray(data) ? data : [];
                    this.meta = {};
                }
            } else {
                console.error('Failed to fetch followups');
                auth.showNotification('Failed to load follow-up reminders', 'error');
                this.followups = [];
                this.meta = {};
            }
        } catch (error) {
            console.error('Error fetching followups:', error);
            auth.showNotification('Error loading follow-up reminders', 'error');
            this.followups = [];
            this.meta = {};
        }
    }

    render() {
        if (!this.tbody) return;

        this.tbody.innerHTML = '';

        if (this.followups.length === 0) {
            if (this.emptyState) this.emptyState.classList.remove('hidden');
            if (this.paginationContainer) this.paginationContainer.innerHTML = '';
            return;
        }

        if (this.emptyState) this.emptyState.classList.add('hidden');

        this.followups.forEach(f => {
            const tr = document.createElement('tr');
            tr.className = 'hover:bg-gray-50 transition-colors';

            // Format dates using the global formatDateTime function (12-hour format with AM/PM)
            const dateTime = window.formatDateTime(f.date_time);
            const createdAt = window.formatDateTime(f.created_at);

            // Status Styles
            let statusClass = 'bg-gray-100 text-gray-800';
            if (f.status === 'pending') statusClass = 'bg-yellow-100 text-yellow-800';
            if (f.status === 'completed') statusClass = 'bg-green-100 text-green-800';
            if (f.status === 'cancelled') statusClass = 'bg-red-100 text-red-800';

            tr.innerHTML = `
        <td class="px-4 py-3 sm:px-6 sm:py-4" data-label="Contact:">
            <div class="font-medium text-gray-900">${f.contact_name || 'No Name'}</div>
        </td>
        <td class="px-4 py-3 sm:px-6 sm:py-4 text-sm text-gray-900" data-label="Phone:">${f.phone}</td>
        <td class="px-4 py-3 sm:px-6 sm:py-4" data-label="Message:">
            <div class="text-sm text-gray-500 max-w-xs truncate" title="${f.message || ''}">${f.message || '-'}</div>
        </td>
        <td class="px-4 py-3 sm:px-6 sm:py-4 text-sm text-gray-900" data-label="User:">${f.user_name || 'Unknown'}</td>
        <td class="px-4 py-3 sm:px-6 sm:py-4 text-sm text-gray-900" data-label="Date/Time:">
            ${dateTime}

        </td>
        <td class="px-4 py-3 sm:px-6 sm:py-4" data-label="Status:">
            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusClass}">
            ${f.status.toUpperCase()}
            </span>
        </td>
         <td class="px-4 py-3 sm:px-6 sm:py-4 text-sm text-gray-500" data-label="Created:">${createdAt}</td>
      `;
            this.tbody.appendChild(tr);
        });

        this.renderPagination();
    }

    renderPagination() {
        if (!this.paginationContainer) return;

        if (!this.meta || !this.meta.pages || this.meta.pages <= 1) {
            this.paginationContainer.innerHTML = '';
            return;
        }

        const { page, per_page, total, pages, has_next, has_prev } = this.meta;
        const start = Math.min((page - 1) * per_page + 1, total);
        const end = Math.min(page * per_page, total);

        this.paginationContainer.innerHTML = `
          <div class="flex items-center justify-between border-t border-gray-200 bg-white px-4 py-3 sm:px-6">
            <div class="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
              <div>
                <p class="text-sm text-gray-700">
                  Showing <span class="font-medium">${start}</span> to <span class="font-medium">${end}</span> of <span class="font-medium">${total}</span> results
                </p>
              </div>
              <div>
                <nav class="isolate inline-flex -space-x-px rounded-md shadow-sm" aria-label="Pagination">
                    <!-- Prev -->
                    <button onclick="followupManager.changePage(${page - 1})" ${!has_prev ? 'disabled' : ''} 
                        class="relative inline-flex items-center rounded-l-md px-2 py-2 ring-1 ring-inset ring-gray-300 focus:z-20 focus:outline-offset-0 ${!has_prev ? 'text-gray-300 cursor-not-allowed' : 'text-gray-400 hover:bg-gray-50'}">
                        <span class="sr-only">Previous</span>
                        <i class="fas fa-chevron-left h-4 w-4"></i>
                    </button>
                    
                    <!-- Info -->
                    <span class="relative inline-flex items-center px-4 py-2 text-sm font-semibold text-gray-900 ring-1 ring-inset ring-gray-300 focus:outline-offset-0">
                        Page ${page} of ${pages}
                    </span>

                    <!-- Next -->
                    <button onclick="followupManager.changePage(${page + 1})" ${!has_next ? 'disabled' : ''}
                        class="relative inline-flex items-center rounded-r-md px-2 py-2 ring-1 ring-inset ring-gray-300 focus:z-20 focus:outline-offset-0 ${!has_next ? 'text-gray-300 cursor-not-allowed' : 'text-gray-400 hover:bg-gray-50'}">
                        <span class="sr-only">Next</span>
                        <i class="fas fa-chevron-right h-4 w-4"></i>
                    </button>
                </nav>
              </div>
            </div>
          </div>
        `;
    }

    async changePage(newPage) {
        if (newPage < 1 || (this.meta.pages && newPage > this.meta.pages)) return;
        this.page = newPage;
        await this.fetchFollowups();
        this.render();
    }
}

// Initialize and expose
const followupManager = new FollowupManager();
window.followupManager = followupManager;
