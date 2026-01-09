/************************************************************
 *  ADMINS MANAGER – SUPER ADMIN DASHBOARD
 ************************************************************/
class AdminsManager {
    constructor() {
        this.admins = [];
        // Init handled by index.html calls
    }

    /************************************************************
     * CREATE ADMIN
     ************************************************************/
    async createAdmin() {
        const name = document.getElementById("adminName").value.trim();
        const email = document.getElementById("adminEmail").value.trim();
        const password = document.getElementById("adminPassword").value.trim();
        const confirmPassword = document.getElementById("adminConfirmPassword").value.trim();
        const userLimit = Number(document.getElementById("userLimit").value || 10);
        const expiryRaw = document.getElementById("expiryDate").value;

        if (!name || !email || !password || !expiryRaw) {
            auth.showNotification("Please fill all fields", "error");
            return;
        }

        if (password !== confirmPassword) {
            auth.showNotification("Passwords do not match", "error");
            return;
        }

        const payload = {
            name,
            email,
            password,
            user_limit: userLimit,
            expiry_date: expiryRaw // Backend expects YYYY-MM-DD
        };

        try {
            const response = await auth.makeAuthenticatedRequest(
                "/api/superadmin/create-admin",
                {
                    method: "POST",
                    body: JSON.stringify(payload)
                }
            );

            const data = await response.json();

            if (response.ok) {
                auth.showNotification("Admin created successfully!", "success");

                // Reset form and close modal
                document.getElementById("createAdminForm").reset();
                document.getElementById("createAdminModal").classList.add("hidden");

                this.loadAdmins();

            } else {
                auth.showNotification(data.error || "Failed to create admin", "error");
            }

        } catch (error) {
            console.error("CREATE ADMIN ERROR:", error);
            auth.showNotification("Server error while creating admin", "error");
        }
    }

    /************************************************************
     * LOAD ADMINS
     ************************************************************/
    async loadAdmins() {
        try {
            const response = await auth.makeAuthenticatedRequest("/api/superadmin/admins");
            const data = await response.json();

            if (response.ok) {
                this.admins = data.admins || [];
                this.renderAdmins();
            } else {
                auth.showNotification(data.error || "Failed to load admins", "error");
            }

        } catch (error) {
            console.error("LOAD ADMINS ERROR:", error);
            auth.showNotification("Server error while loading admins", "error");
        }
    }

    /************************************************************
     * TOGGLE ADMIN STATUS (BLOCK/UNBLOCK)
     ************************************************************/
    async toggleAdminStatus(adminId, currentStatus) {
        if (!confirm(`Are you sure you want to ${currentStatus ? 'block' : 'unblock'} this admin?`)) {
            return;
        }

        try {
            const response = await auth.makeAuthenticatedRequest(
                `/api/superadmin/admin/${adminId}/status`,
                { method: "PUT" }
            );
            const data = await response.json();

            if (response.ok) {
                auth.showNotification(data.message, "success");
                this.loadAdmins();
            } else {
                auth.showNotification(data.error || "Failed to update status", "error");
            }

        } catch (error) {
            console.error("TOGGLE STATUS ERROR:", error);
            auth.showNotification("Server error", "error");
        }
    }

    /************************************************************
     * DELETE ADMIN
     ************************************************************/
    async deleteAdmin(adminId) {
        if (!confirm("Are you sure you want to delete this admin? This action cannot be undone.")) {
            return;
        }

        try {
            const response = await auth.makeAuthenticatedRequest(
                `/api/superadmin/admin/${adminId}`,
                { method: "DELETE" }
            );
            const data = await response.json();

            if (response.ok) {
                auth.showNotification(data.message, "success");
                this.loadAdmins();
            } else {
                auth.showNotification(data.error || "Failed to delete admin", "error");
            }

        } catch (error) {
            console.error("DELETE ADMIN ERROR:", error);
            auth.showNotification("Server error", "error");
        }
    }

    /************************************************************
     * EDIT ADMIN
     ************************************************************/
    openEditModal(id, limit, expiry) {
        document.getElementById("editAdminId").value = id;
        document.getElementById("editUserLimit").value = limit;
        if (expiry && expiry !== 'undefined') {
            document.getElementById("editExpiryDate").value = expiry;
        }
        document.getElementById("editAdminModal").classList.remove("hidden");
    }

    async updateAdmin() {
        const id = document.getElementById("editAdminId").value;
        const limit = document.getElementById("editUserLimit").value;
        const expiry = document.getElementById("editExpiryDate").value;

        if (!limit || !expiry) {
            auth.showNotification("Please fill all fields", "error");
            return;
        }

        try {
            const response = await auth.makeAuthenticatedRequest(
                `/api/superadmin/admin/${id}`,
                {
                    method: "PUT",
                    body: JSON.stringify({
                        user_limit: limit,
                        expiry_date: expiry
                    })
                }
            );
            const data = await response.json();

            if (response.ok) {
                auth.showNotification("Admin updated successfully", "success");
                document.getElementById("editAdminModal").classList.add("hidden");
                this.loadAdmins();
            } else {
                auth.showNotification(data.error || "Failed to update admin", "error");
            }

        } catch (error) {
            console.error("UPDATE ADMIN ERROR:", error);
            auth.showNotification("Server error", "error");
        }
    }

    /************************************************************
     * RENDER ADMIN TABLE
     ************************************************************/
    renderAdmins() {
        const tableBody = document.getElementById("admins-table-body");
        if (!tableBody) return;

        if (this.admins.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="6" class="py-10 text-center text-gray-500">
                        <i class="fas fa-users-slash text-3xl mb-2 text-gray-300"></i>
                        <p>No admins found</p>
                    </td>
                </tr>
            `;
            return;
        }

        tableBody.innerHTML = this.admins
            .map(admin => {
                let exp = admin.expiry_date ? new Date(admin.expiry_date) : null;
                let expiryStr = exp && !isNaN(exp) ? exp.toLocaleDateString() : "N/A";

                let status =
                    !admin.is_active
                        ? `<span class="bg-red-100 text-red-800 px-2.5 py-0.5 rounded-full text-xs font-medium">Inactive</span>`
                        : admin.is_expired
                            ? `<span class="bg-orange-100 text-orange-800 px-2.5 py-0.5 rounded-full text-xs font-medium">Expired</span>`
                            : `<span class="bg-green-100 text-green-800 px-2.5 py-0.5 rounded-full text-xs font-medium">Active</span>`;

                return `
                <tr class="hover:bg-gray-50 transition">

                    <!-- NAME -->
                    <td class="px-6 py-4" data-label="Admin Name">
                        <div class="flex items-center space-x-3">
                            <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-bold text-xs">
                                ${admin.name.substring(0, 2).toUpperCase()}
                            </div>
                            <div class="font-medium text-gray-900">${admin.name}</div>
                        </div>
                    </td>

                    <!-- EMAIL -->
                    <td class="px-6 py-4 text-gray-500" data-label="Email">
                        ${admin.email}
                    </td>

                    <!-- USER LIMIT -->
                    <td class="px-6 py-4 text-gray-500" data-label="User Limit">
                        ${admin.user_limit}
                    </td>

                    <!-- USERS CREATED -->
                    <td class="px-6 py-4" data-label="Users Created">
                        <span class="px-2.5 py-0.5 bg-gray-100 text-gray-800 rounded-full text-xs font-medium">
                            ${admin.user_count} / ${admin.user_limit}
                        </span>
                    </td>

                    <!-- EXPIRY -->
                    <td class="px-6 py-4 text-gray-500" data-label="Expiry Date">
                        ${expiryStr}
                    </td>

                    <!-- STATUS -->
                    <td class="px-6 py-4" data-label="Status">
                        ${status}
                    </td>

                    <!-- ACTIONS -->
                    <td class="px-6 py-4 text-right" data-label="Actions">
                        <div class="flex items-center justify-end space-x-2">
                            <!-- View Users Button -->
                            <button onclick="adminsManager.viewUsers(${admin.id}, '${admin.name}')"
                                class="p-2 rounded hover:bg-purple-50 text-purple-600 transition"
                                title="View Admin Users">
                                <i class="fas fa-users"></i>
                            </button>
                            <!-- Toggle Status Button -->
                            <button onclick="adminsManager.toggleAdminStatus(${admin.id}, ${admin.is_active})"
                                class="p-2 rounded hover:bg-gray-100 text-gray-600 transition"
                                title="${admin.is_active ? 'Block Admin' : 'Unblock Admin'}">
                                <i class="fas ${admin.is_active ? 'fa-ban text-orange-500' : 'fa-check-circle text-green-500'}"></i>
                            </button>

                            <!-- Edit Button -->
                            <button onclick="adminsManager.openEditModal(${admin.id}, '${admin.user_limit}', '${expiryStr !== 'N/A' ? admin.expiry_date.split('T')[0] : ''}')"
                                class="p-2 rounded hover:bg-blue-50 text-blue-600 transition"
                                title="Edit Admin">
                                <i class="fas fa-edit"></i>
                            </button>

                            <!-- Delete Button -->
                            <button onclick="adminsManager.deleteAdmin(${admin.id})"
                                class="p-2 rounded hover:bg-red-50 text-red-600 transition"
                                title="Delete Admin">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </td>

                </tr>
                `;
            })
            .join("");
    }

    /************************************************************
     * VIEW ADMIN USERS
     ************************************************************/
    async viewUsers(adminId, adminName) {
        document.getElementById("viewUsersAdminName").textContent = `Viewing users for ${adminName}`;
        const tableBody = document.getElementById("viewUsersTableBody");
        tableBody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-gray-500"><i class="fas fa-spinner fa-spin mr-2"></i> Loading users...</td></tr>`;

        document.getElementById("viewUsersModal").classList.remove("hidden");

        try {
            const response = await auth.makeAuthenticatedRequest(`/api/superadmin/admin/${adminId}/users`);
            const data = await response.json();

            if (response.ok) {
                if (data.users.length === 0) {
                    tableBody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-gray-500">No users found for this admin</td></tr>`;
                    return;
                }

                tableBody.innerHTML = data.users.map(u => {
                    return `
                    <tr class="hover:bg-gray-50">
                        <td class="px-6 py-3 font-medium text-gray-900" data-label="User Name">${u.name}</td>
                         <td class="px-6 py-3 text-gray-500" data-label="Email">${u.email}</td>
                        <td class="px-6 py-3 text-gray-500" data-label="Phone">${u.phone || '-'}</td>
                        <td class="px-6 py-3 text-gray-500" data-label="Created">${new Date(u.created_at).toLocaleDateString()}</td>
                         <td class="px-6 py-3 text-gray-500" data-label="Last Login">${u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}</td>
                        <td class="px-6 py-3" data-label="Status">
                             ${u.is_active
                            ? '<span class="px-2 py-0.5 rounded-full bg-green-100 text-green-800 text-xs font-medium">Active</span>'
                            : '<span class="px-2 py-0.5 rounded-full bg-red-100 text-red-800 text-xs font-medium">Inactive</span>'}
                        </td>
                    </tr>
                    `
                }).join("");

            } else {
                tableBody.innerHTML = `<tr><td colspan="6" class="px-6 py-4 text-center text-red-500">Failed to load users</td></tr>`;
                auth.showNotification(data.error || "Failed to load users", "error");
            }
        } catch (error) {
            console.error("VIEW USERS ERROR:", error);
            tableBody.innerHTML = `<tr><td colspan="6" class="px-6 py-4 text-center text-red-500">Server error</td></tr>`;
        }
    }
}

/************************************************************
 *  ACTIVITY LOGS MANAGER
 ************************************************************/
class ActivityLogsManager {
    constructor() {
        this.logs = [];
    }

    async loadLogs() {
        try {
            const response = await auth.makeAuthenticatedRequest("/api/superadmin/logs");
            const data = await response.json();

            if (response.ok) {
                this.logs = data.logs || [];
                this.renderLogs();
            } else {
                console.error("Failed to load logs:", data.error);
            }
        } catch (error) {
            console.error("LOAD LOGS ERROR:", error);
        }
    }

    renderLogs() {
        const container = document.getElementById("recent-activity");
        if (!container) return;

        if (this.logs.length === 0) {
            container.innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    <i class="fas fa-clipboard-list text-3xl mb-2 text-gray-300"></i>
                    <p>No recent activity</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm">
                    <thead class="bg-gray-50 text-gray-500 uppercase tracking-wider font-semibold text-xs border-b border-gray-100">
                        <tr>
                            <th class="px-6 py-3">Actor</th>
                            <th class="px-6 py-3">Action</th>
                            <th class="px-6 py-3">Role</th>
                            <th class="px-6 py-3">Date</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100 bg-white">
                        ${this.logs.map(log => this.createRow(log)).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    createRow(log) {
        const date = new Date(log.timestamp).toLocaleString();

        let roleBadge = "";
        if (log.role === "super_admin") {
            roleBadge = `<span class="bg-purple-100 text-purple-800 px-2 py-0.5 rounded-full text-xs font-medium">Super Admin</span>`;
        } else if (log.role === "admin") {
            roleBadge = `<span class="bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full text-xs font-medium">Admin</span>`;
        } else {
            roleBadge = `<span class="bg-gray-100 text-gray-800 px-2 py-0.5 rounded-full text-xs font-medium">User</span>`;
        }

        return `
            <tr class="hover:bg-gray-50 transition">
                <td class="px-6 py-3 font-medium text-gray-900">${log.admin_name}</td>
                <td class="px-6 py-3 text-gray-600">${log.action_type}</td>
                <td class="px-6 py-3">${roleBadge}</td>
                <td class="px-6 py-3 text-gray-500 text-xs">${date}</td>
            </tr>
        `;
    }
}
