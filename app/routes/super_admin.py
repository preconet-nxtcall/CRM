from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, create_access_token, get_jwt_identity
from datetime import datetime
from ..models import db, SuperAdmin, Admin, User, ActivityLog, UserRole
import re

bp = Blueprint("super_admin", __name__, url_prefix="/api/superadmin")


# =========================================================
# HELPERS
# =========================================================
def _validate_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email or "") is not None


def _safe_enum_value(role):
    """Convert Enum to plain string"""
    try:
        return role.value
    except:
        return str(role)


# =========================================================
# SUPER ADMIN LOGIN
# =========================================================
@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    print(f"DEBUG LOGIN: Attempting login for email: {email}")
    super_admin = SuperAdmin.query.filter_by(email=email).first()
    
    # -----------------------------------------------------
    # AUTO-FIX FOR EMPTY DB
    # If using default email and it doesn't exist, create it immediately.
    # -----------------------------------------------------
    if not super_admin and email == "nxtcall.app@gmail.com":
        print("DEBUG LOGIN: Default SuperAdmin missing in DB. Auto-creating now...")
        try:
            super_admin = SuperAdmin(name="Super Admin", email="nxtcall.app@gmail.com")
            super_admin.set_password("kolkata@2025")
            db.session.add(super_admin)
            db.session.commit()
            print("DEBUG LOGIN: Auto-creation SUCCESS.")
        except Exception as e:
            print(f"DEBUG LOGIN: Auto-creation FAILED: {e}")
            db.session.rollback()

    
    if not super_admin:
        print("DEBUG LOGIN: SuperAdmin not found in DB.")
        # DIAGNOSTIC: List all super admins to see what IS there
        all_admins = SuperAdmin.query.all()
        print(f"DEBUG LOGIN: Total SuperAdmins in DB: {len(all_admins)}")
        for a in all_admins:
            print(f"DEBUG LOGIN: Existing Admin - ID: {a.id}, Email: {a.email}, Name: {a.name}")
            
        return jsonify({"error": "Invalid credentials"}), 401
        
    print(f"DEBUG LOGIN: Found SuperAdmin ID: {super_admin.id}, Name: {super_admin.name}")
    print(f"DEBUG LOGIN: Stored Hash: {super_admin.password_hash}")
    
    is_valid = super_admin.check_password(password)
    print(f"DEBUG LOGIN: Password Check Result: {is_valid}")

    if not is_valid:
        print("DEBUG LOGIN: Password mismatch.")
        return jsonify({"error": "Invalid credentials"}), 401

    from datetime import timedelta
    token = create_access_token(
        identity=str(super_admin.id),
        additional_claims={"role": "super_admin"},
        expires_delta=timedelta(days=365)
    )

    return jsonify({
        "access_token": token,
        "user": {
            "id": super_admin.id,
            "name": super_admin.name,
            "email": super_admin.email,
            "role": "super_admin",
        }
    }), 200


# =========================================================
# EMERGENCY FIX ROUTE (To fix DB state remotely)
# =========================================================
@bp.route("/emergency-fix", methods=["GET"])
def emergency_fix():
    try:
        email = "nxtcall.app@gmail.com"
        password = "kolkata@2025"
        
        # 1. Try exact match
        admin = SuperAdmin.query.filter_by(email=email).first()
        
        action = "Updated existing exact match"
        
        if not admin:
            # 2. Try finding ANY super admin and updating them (to handle 'ghost' emails)
            admin = SuperAdmin.query.first()
            if admin:
                old_email = admin.email
                admin.email = email
                admin.name = "Super Admin"
                action = f"Renamed existing admin from {old_email}"
            else:
                # 3. Create fresh
                admin = SuperAdmin(name="Super Admin", email=email)
                db.session.add(admin)
                action = "Created new Super Admin"
        
        # Force password reset
        admin.set_password(password)
        db.session.commit()
        
        return jsonify({
            "status": "SUCCESS",
            "message": "Super Admin Credentials Fixed",
            "details": action,
            "credentials": {
                "email": admin.email,
                "password": password
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================================
# CREATE ADMIN
# =========================================================
@bp.route("/create-admin", methods=["POST"])
@jwt_required()
def create_admin():
    super_admin_id = get_jwt_identity()

    if not SuperAdmin.query.get(super_admin_id):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    user_limit = int(data.get("user_limit", 10))
    expiry_date_raw = data.get("expiry_date")

    # Validate required fields
    if not all([name, email, password, expiry_date_raw]):
        return jsonify({"error": "All fields required"}), 400

    # Validate email format
    if not _validate_email(email):
        return jsonify({"error": "Invalid email format"}), 400

    # Check duplicate email
    if Admin.query.filter_by(email=email).first():
        return jsonify({"error": "Admin email already exists"}), 400

    # Convert expiry date (YYYY-MM-DD)
    try:
        expiry_date = datetime.strptime(expiry_date_raw, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "expiry_date must be YYYY-MM-DD"}), 400

    # Create new admin
    new_admin = Admin(
        name=name,
        email=email,
        user_limit=user_limit,
        expiry_date=expiry_date,
        created_by=super_admin_id,
    )
    new_admin.set_password(password)

    db.session.add(new_admin)
    db.session.commit()

    # Log the activity
    log = ActivityLog(
        actor_role=UserRole.SUPER_ADMIN,
        actor_id=super_admin_id,
        action=f"Created Admin: {name}",
        target_type="admin",
        target_id=new_admin.id
    )
    db.session.add(log)
    db.session.commit()

    # Automatic Notification
    try:
        from app.services.notification_service import NotificationService
        import logging
        
        logging.info(f"Attempting to send welcome email to {email}")
        result = NotificationService.send_welcome_notification(
            name=name,
            username=email,
            password=password,
            expiry_date=expiry_date,
            phone=None,
            email=email
        )
        if result:
            logging.info(f"Welcome email sent successfully to {email}")
        else:
            logging.warning(f"Welcome email failed to send to {email} - check ZEPTOMAIL credentials")
            
    except Exception as e:
        # Catch ALL errors so we never fail the request after DB commit
        import traceback
        traceback.print_exc()
        try:
            logging.error(f"CRITICAL: Failed to send notification to {email}: {e}", exc_info=True)
        except:
            print(f"CRITICAL: Failed to send notification to {email}: {e}")

    return jsonify({"message": "Admin created successfully"}), 201


# =========================================================
# GET ALL ADMINS (SUPER ADMIN)
# =========================================================
@bp.route("/admins", methods=["GET"])
@jwt_required()
def get_admins():
    try:
        admins = Admin.query.order_by(Admin.created_at.desc()).all()
        result = []

        for a in admins:
            user_count = User.query.filter_by(admin_id=a.id).count()

            result.append({
                "id": a.id,
                "name": a.name,
                "email": a.email,
                "user_limit": a.user_limit,
                "user_count": user_count,
                "is_active": a.is_active,
                "is_expired": a.is_expired(),
                "created_at": a.created_at.isoformat(),
                "last_login": a.last_login.isoformat() if a.last_login else None,
                "expiry_date": a.expiry_date.isoformat(),
            })

        return jsonify({"admins": result}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================================
# DASHBOARD STATS
# =========================================================
@bp.route("/dashboard-stats", methods=["GET"])
@jwt_required()
def dashboard_stats():
    try:
        super_admin_id = get_jwt_identity()
        super_admin = SuperAdmin.query.get(super_admin_id)

        stats = {
            "total_admins": Admin.query.count(),
            "active_admins": Admin.query.filter_by(is_active=True).count(),
            "expired_admins": Admin.query.filter(Admin.expiry_date < datetime.utcnow()).count(),
            "total_users": User.query.count(),
            "super_admin_name": super_admin.name if super_admin else "Super Admin",
            "super_admin_email": super_admin.email if super_admin else "superadmin@example.com",
        }

        return jsonify({"stats": stats}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================================
# GET LATEST ACTIVITY LOGS
# =========================================================
@bp.route("/logs", methods=["GET"])
@jwt_required()
def activity_logs():
    try:
        # Verify super admin
        super_admin_id = get_jwt_identity()
        if not SuperAdmin.query.get(super_admin_id):
            return jsonify({"error": "Unauthorized"}), 401
        
        try:
            # Fetch logs directly (simpler query)
            logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(50).all()
        except Exception as table_error:
            # Table might not exist yet - return empty logs
            print(f"ActivityLog table error: {table_error}")
            return jsonify({"logs": []}), 200

        formatted = []
        for log in logs:
            display_name = "Unknown"
            
            try:
                if log.actor_role == UserRole.SUPER_ADMIN:
                    display_name = "Super Admin"
                elif log.actor_role == UserRole.ADMIN:
                    admin = Admin.query.get(log.actor_id)
                    display_name = admin.name if admin else f"Admin #{log.actor_id} (Deleted)"
                elif log.actor_role == UserRole.USER:
                    user = User.query.get(log.actor_id)
                    display_name = f"User #{log.actor_id}" # Simplify as user name might not be needed or User model issue
                    if user:
                         display_name = user.name
            except Exception as inner_e:
                print(f"Error processing log {log.id}: {inner_e}")
                display_name = "Error Resolving Name"

            formatted.append({
                "id": log.id,
                "admin_name": display_name, 
                "action_type": log.action,
                "timestamp": log.timestamp.isoformat(),
                "role": log.actor_role.value if hasattr(log.actor_role, 'value') else str(log.actor_role)
            })

        return jsonify({"logs": formatted}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Return empty logs instead of 500 error
        return jsonify({"logs": []}), 200


# =========================================================
# DELETE ACTIVITY LOGS
# =========================================================
@bp.route("/logs", methods=["DELETE"])
@jwt_required()
def delete_activity_logs():
    try:
        # Verify super admin
        super_admin_id = get_jwt_identity()
        if not SuperAdmin.query.get(super_admin_id):
            return jsonify({"error": "Unauthorized"}), 401

        # Delete all logs
        num_deleted = db.session.query(ActivityLog).delete()
        db.session.commit()

        # Create a new log for this action
        log = ActivityLog(
            actor_role=UserRole.SUPER_ADMIN,
            actor_id=super_admin_id,
            action="Deleted all activity logs",
            target_type="system",
            target_id=0
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({"message": f"Deleted {num_deleted} logs"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# =========================================================
# TOGGLE ADMIN STATUS (BLOCK/UNBLOCK)
# =========================================================
@bp.route("/admin/<int:admin_id>/status", methods=["PUT"])
@jwt_required()
def toggle_admin_status(admin_id):
    try:
        # Verify super admin
        super_admin_id = get_jwt_identity()
        if not SuperAdmin.query.get(super_admin_id):
            return jsonify({"error": "Unauthorized"}), 401

        admin = Admin.query.get(admin_id)
        if not admin:
            return jsonify({"error": "Admin not found"}), 404

        # Toggle status
        admin.is_active = not admin.is_active
        db.session.commit()

        action = "Unblocked" if admin.is_active else "Blocked"

        # Log activity
        log = ActivityLog(
            actor_role=UserRole.SUPER_ADMIN,
            actor_id=super_admin_id,
            action=f"{action} Admin: {admin.name}",
            target_type="admin",
            target_id=admin.id
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            "message": f"Admin {action.lower()} successfully",
            "is_active": admin.is_active
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500



# =========================================================
# UPDATE ADMIN (Limit & Expiry)
# =========================================================
@bp.route("/admin/<int:admin_id>", methods=["PUT"])
@jwt_required()
def update_admin(admin_id):
    try:
        # Verify super admin
        super_admin_id = get_jwt_identity()
        if not SuperAdmin.query.get(super_admin_id):
            return jsonify({"error": "Unauthorized"}), 401

        admin = Admin.query.get(admin_id)
        if not admin:
            return jsonify({"error": "Admin not found"}), 404

        data = request.get_json()

        # Update fields if present
        if "user_limit" in data:
            admin.user_limit = int(data["user_limit"])

        if "expiry_date" in data:
            try:
                from datetime import datetime
                admin.expiry_date = datetime.strptime(data["expiry_date"], "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"error": "Invalid date format (YYYY-MM-DD required)"}), 400

        db.session.commit()

        # Log activity
        log = ActivityLog(
            actor_role=UserRole.SUPER_ADMIN,
            actor_id=super_admin_id,
            action=f"Updated Admin: {admin.name}",
            target_type="admin",
            target_id=admin_id
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({"message": "Admin updated successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# =========================================================
# DELETE ADMIN
# =========================================================
@bp.route("/admin/<int:admin_id>", methods=["DELETE"])
@jwt_required()
def delete_admin(admin_id):
    try:
        # Verify super admin
        super_admin_id = get_jwt_identity()
        if not SuperAdmin.query.get(super_admin_id):
            return jsonify({"error": "Unauthorized"}), 401

        admin = Admin.query.get(admin_id)
        if not admin:
            return jsonify({"error": "Admin not found"}), 404

        # Delete admin
        admin_name = admin.name
        db.session.delete(admin)
        db.session.commit()

        # Log activity
        log = ActivityLog(
            actor_role=UserRole.SUPER_ADMIN,
            actor_id=super_admin_id,
            action=f"Deleted Admin: {admin_name}",
            target_type="admin",
            target_id=admin_id
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({"message": "Admin deleted successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route("/admin/<int:admin_id>/users", methods=["GET"])
@jwt_required()
def get_admin_users(admin_id):
    try:
        super_admin_id = get_jwt_identity()
        if not SuperAdmin.query.get(super_admin_id):
            return jsonify({"error": "Unauthorized"}), 401
        
        users = User.query.filter_by(admin_id=admin_id).all()
        result = []
        for u in users:
            result.append({
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "phone": u.phone,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None
            })
            
        return jsonify({"users": result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================================================
# GET EXPIRED ADMINS
# =========================================================
@bp.route("/expired-admins", methods=["GET"])
@jwt_required()
def get_expired_admins():
    try:
        # Verify super admin
        super_admin_id = get_jwt_identity()
        if not SuperAdmin.query.get(super_admin_id):
            return jsonify({"error": "Unauthorized"}), 401

        # Query expired admins
        expired_admins = Admin.query.filter(Admin.expiry_date < datetime.utcnow()).order_by(Admin.expiry_date.desc()).all()
        result = []

        for a in expired_admins:
            user_count = User.query.filter_by(admin_id=a.id).count()
            result.append({
                "id": a.id,
                "name": a.name,
                "email": a.email,
                "user_limit": a.user_limit,
                "user_count": user_count,
                "is_active": a.is_active,
                "is_expired": True,
                "created_at": a.created_at.isoformat(),
                "expiry_date": a.expiry_date.isoformat(),
            })

        return jsonify({"admins": result}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500