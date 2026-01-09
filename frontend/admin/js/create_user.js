// Wait for DOM to be ready
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("createUserForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const payload = {
            name: document.getElementById("userName")?.value.trim(),
            email: document.getElementById("userEmail")?.value.trim(),
            password: document.getElementById("userPassword")?.value,
            phone: document.getElementById("userPhone")?.value.trim(),
        };

        // Required fields
        if (!payload.name || !payload.email || !payload.password) {
            auth.showNotification("Name, Email, and Password are required", "error");
            return;
        }

        // Email validation
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(payload.email)) {
            auth.showNotification("Enter a valid email address", "error");
            return;
        }

        // Password length validation
        if (payload.password.length < 6) {
            auth.showNotification("Password must be at least 6 characters", "error");
            return;
        }

        // Disable submit + show loading
        const submitBtn = form.querySelector('button[type="submit"]');
        const oldText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = "Creating...";

        try {
            const res = await auth.makeAuthenticatedRequest("/api/admin/create-user", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",  // FIXED
                },
                body: JSON.stringify(payload),
            });

            const data = await res.json();

            if (res.ok) {
                auth.showNotification("User created successfully!", "success");
                form.reset();

                // Auto-refresh user list safely
                window.usersManager?.loadUsers?.();
            } else {
                auth.showNotification(data.error || "Error creating user", "error");
            }
        } catch (err) {
            console.error("Create User Error:", err);
            auth.showNotification("Server or network error", "error");
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = oldText;
        }
    });
});