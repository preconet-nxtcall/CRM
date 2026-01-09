# app/routes/users.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    jwt_required,
    create_access_token,
    get_jwt_identity,
    get_jwt
)
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
import re

from app.models import db, User, Admin, ActivityLog, UserRole
from app.auth_helpers import get_authorized_user

bp = Blueprint("users", __name__, url_prefix="/api/users")

# -------------------------
# Regex validators
# -------------------------
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


def validate_email(email: str):
    return bool(email and EMAIL_RE.match(email))


def validate_phone(phone: str):
    return bool(phone and PHONE_RE.match(phone))


def iso(dt):
    """Convert datetime to ISO safely."""
    if dt is None:
        return None
    try:
        if dt.tzinfo:
            return dt.astimezone(timezone.utc).isoformat()
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except:
        return str(dt)


# ============================================================
# USER REGISTER (ADMIN ONLY)
# ============================================================
@bp.route("/register", methods=["POST"])
@jwt_required()
def register():
    try:
        claims = get_jwt()
        if claims.get("role") != "admin":
            return jsonify({"error": "Admin access only"}), 403

        admin_id = int(get_jwt_identity())
        admin = Admin.query.get(admin_id)

        if not admin or not admin.is_active:
            return jsonify({"error": "Admin not found or inactive"}), 403

        if admin.expiry_date:
            today = datetime.utcnow().date()
            expiry = admin.expiry_date.date() if hasattr(admin.expiry_date, "date") else admin.expiry_date
            if expiry < today:
                return jsonify({"error": "Admin subscription expired"}), 403

        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password")
        phone = (data.get("phone") or "").strip() or None

        if not name or not email or not password:
            return jsonify({"error": "name, email and password required"}), 400

        if not validate_email(email):
            return jsonify({"error": "Invalid email"}), 400

        if phone and not validate_phone(phone):
            return jsonify({"error": "Invalid phone"}), 400

        # Email exists?
        if User.query.filter(func.lower(User.email) == email).first():
            return jsonify({"error": "Email already exists"}), 400

        # User limit
        total_users = User.query.filter_by(admin_id=admin.id).count()
        if total_users >= admin.user_limit:
            return jsonify({"error": "Admin user limit reached"}), 400

        user = User(
            name=name,
            email=email,
            phone=phone,
            admin_id=admin.id,
            created_at=datetime.utcnow()
        )
        user.set_password(password)

        # Log creation
        log = ActivityLog(
            actor_role=UserRole.ADMIN,
            actor_id=admin.id,
            action=f"Created user {email}",
            target_type="user"
        )

        db.session.add(user)
        db.session.flush()
        log.target_id = user.id
        db.session.add(log)
        db.session.commit()

        return jsonify({
            "message": "User created successfully",
            "user": {"id": user.id, "name": user.name, "email": user.email, "phone": user.phone}
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Internal server error", "detail": str(e)}), 400


# ============================================================
# USER LOGIN
# ============================================================
@bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json() or {}

        email = (data.get("email") or "").strip().lower()
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "Email & password required"}), 400

        user = User.query.filter(func.lower(User.email) == email).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
            
        if not user.check_password(password):
            return jsonify({"error": "Invalid password"}), 401

        if not user.is_active:
            return jsonify({"error": "Account deactivated"}), 403

        # Check for Blocked/Suspended
        if getattr(user, 'status', 'active') == 'blocked' or getattr(user, 'is_suspended', False):
             return jsonify({"error": "Your account has been blocked/suspended by Admin."}), 403

        # Validate admin
        admin = Admin.query.get(user.admin_id)
        if not admin:
            return jsonify({"error": "Admin removed"}), 403

        # SAFE expiry check
        if admin.expiry_date:
            today = datetime.utcnow().date()
            expiry = admin.expiry_date.date() if hasattr(admin.expiry_date, "date") else admin.expiry_date

            if expiry < today:
                return jsonify({"error": "Your admin subscription has expired"}), 403

        # Update login time & session
        import uuid
        session_id = uuid.uuid4().hex
        try:
            user.last_login = datetime.utcnow()
            user.current_session_id = session_id
            db.session.commit()
        except:
            db.session.rollback()
            return jsonify({"error": "Login failed (Session Save Error)"}), 500

        token = create_access_token(
            identity=str(user.id),
            expires_delta=timedelta(days=365), # Long-lived token; rely on guard for revocation
            additional_claims={
                "role": "user",
                "session_id": session_id
            }
        )

        return jsonify({
            "access_token": token,
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "role": "user",
                "last_sync": iso(user.last_sync)
            }
        }), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "detail": str(e)}), 400


# ============================================================
# USER LOGOUT
# ============================================================
@bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    try:
        identity = get_jwt_identity()
        user = User.query.get(int(identity))
        
        if user:
            # Clear session to invalidate token
            user.current_session_id = None
            db.session.commit()
            
        return jsonify({"message": "Logged out successfully"}), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "detail": str(e)}), 400


# ============================================================
# PROFILE (me)
# ============================================================
# Local get_authorized_user removed (moved to app/auth_helpers.py)


# ============================================================
# PROFILE (me)
# ============================================================
@bp.route("/me", methods=["GET"])
@jwt_required()
def get_me():
    try:
        user, error_resp = get_authorized_user()
        if error_resp:
            return error_resp

        return jsonify({
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "created_at": iso(user.created_at),
                "last_login": iso(user.last_login),
                "last_sync": iso(user.last_sync),
            }
        }), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "detail": str(e)}), 400


# ============================================================
# UPDATE PROFILE
# ============================================================
@bp.route("/update", methods=["PUT", "PATCH"])
@jwt_required()
def update_profile():
    try:
        user = User.query.get(int(get_jwt_identity()))
        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json() or {}
        name = data.get("name")
        phone = data.get("phone")

        if name:
            name = name.strip()
            if not name:
                return jsonify({"error": "Invalid name"}), 400
            user.name = name

        if phone:
            phone = phone.strip()
            if phone and not validate_phone(phone):
                return jsonify({"error": "Invalid phone"}), 400
            user.phone = phone or None

        db.session.commit()

        return jsonify({"message": "Profile updated"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Internal server error", "detail": str(e)}), 400


# ============================================================
# SYNC DATA
# ============================================================
@bp.route("/sync", methods=["POST"])
@jwt_required()
def sync_data():
    try:
        user = User.query.get(int(get_jwt_identity()))
        if not user:
            return jsonify({"error": "User not found"}), 404

        user.last_sync = datetime.utcnow()
        db.session.commit()

        return jsonify({
            "message": "Data synced",
            "last_sync": iso(user.last_sync)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Internal server error", "detail": str(e)}), 400


# ============================================================
# SYNC STATUS
# ============================================================
@bp.route("/sync-status", methods=["GET"])
@jwt_required()
def sync_status():
    try:
        user = User.query.get(int(get_jwt_identity()))
        if not user:
            return jsonify({"error": "User not found"}), 404

        from app.models import CallHistory
        count = CallHistory.query.filter_by(user_id=user.id).count()

        return jsonify({
            "sync_status": {
                "last_sync": iso(user.last_sync),
                "call_history_count": count
            }
        }), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "detail": str(e)}), 400
