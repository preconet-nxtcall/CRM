from flask import Blueprint, request, jsonify
from app.models import db, User, Admin, SuperAdmin, PasswordReset
from app.services.notification_service import NotificationService
from datetime import datetime, timedelta
import uuid

bp = Blueprint("auth_pwd", __name__, url_prefix="/api/auth")

# =========================================================
# 1. FORGOT PASSWORD (REQUEST RESET)
# =========================================================
@bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        data = request.get_json()
        email = (data.get("email") or "").strip().lower()

        if not email:
            return jsonify({"error": "Email is required"}), 400

        # Check if email exists in Admin or SuperAdmin role
        admin = Admin.query.filter_by(email=email).first()
        super_admin = SuperAdmin.query.filter_by(email=email).first()

        if not (admin or super_admin):
            # Security: Don't reveal if user exists. Just say email sent if valid.
            return jsonify({"message": "If this email is registered, you will receive a reset link."}), 200

        # Generate Token
        token = uuid.uuid4().hex
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        # Save to DB
        reset_entry = PasswordReset(
            email=email,
            token=token,
            expires_at=expires_at
        )
        db.session.add(reset_entry)
        db.session.commit()

        # Send Email
        origin = request.headers.get("Origin") or "https://call-manager-pro.onrender.com"
        reset_link = f"{origin}/admin/reset_password.html?token={token}"

        NotificationService.send_password_reset_email(email, reset_link)

        return jsonify({"message": "If this email is registered, you will receive a reset link."}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# =========================================================
# 2. RESET PASSWORD (VERIFY & UPDATE)
# =========================================================
@bp.route("/reset-password", methods=["POST"])
def reset_password():
    try:
        data = request.get_json()
        token = data.get("token")
        new_password = data.get("password")

        if not token or not new_password:
            return jsonify({"error": "Token and password required"}), 400

        # Verify Token
        reset_entry = PasswordReset.query.filter_by(token=token).first()

        if not reset_entry:
            return jsonify({"error": "Invalid token"}), 400

        if not reset_entry.is_valid():
            return jsonify({"error": "Token expired or already used"}), 400

        # Find User to Update
        email = reset_entry.email
        
        user = User.query.filter_by(email=email).first()
        admin = Admin.query.filter_by(email=email).first()
        super_admin = SuperAdmin.query.filter_by(email=email).first()

        if super_admin:
            super_admin.set_password(new_password)
            updated = True
        elif admin:
            admin.set_password(new_password)
            updated = True
        
        if not updated:
            return jsonify({"error": "User no longer exists"}), 404

        # Mark token as used
        reset_entry.used = True
        db.session.commit()

        return jsonify({"message": "Password reset successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
