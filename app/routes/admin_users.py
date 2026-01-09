from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.models import db
from ..models import User, Admin, Attendance, CallHistory, ActivityLog, UserRole

admin_user_bp = Blueprint("admin_user", __name__, url_prefix="/api/admin")


# ----------------------------------------
# Role check helper
# ----------------------------------------
def admin_required():
    claims = get_jwt()
    return claims.get("role") == "admin"


# ----------------------------------------
# GET USER FULL DATA (Profile + Sync Summary)
# ----------------------------------------
@admin_user_bp.route("/user-data/<int:user_id>", methods=["GET"])
@jwt_required()
def admin_get_user_data(user_id):
    try:
        if not admin_required():
            return jsonify({"error": "Admin only"}), 403

        admin_id = int(get_jwt_identity())

        # Verify admin owns this user
        user = User.query.get(user_id)
        if not user or user.admin_id != admin_id:
            return jsonify({"error": "Unauthorized user access"}), 403

        # Attendance count
        attendance_count = Attendance.query.filter_by(user_id=user_id).count()

        # Call history count
        call_count = CallHistory.query.filter_by(user_id=user_id).count()

        return jsonify({
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "is_active": user.is_active,
                "performance_score": user.performance_score,
                "created_at": user.created_at.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "last_sync": (user.last_sync.isoformat() + 'Z') if user.last_sync else None,
                "attendance_records": attendance_count,
                "call_records": call_count
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ----------------------------------------
# DELETE USER (Account + Data)
# ----------------------------------------
@admin_user_bp.route("/delete-user/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    if not admin_required():
        return jsonify({"error": "Admin only"}), 403

    admin_id = int(get_jwt_identity())

    # Check if user exists and belongs to this admin
    user = User.query.get(user_id)
    if not user or user.admin_id != admin_id:
        return jsonify({"error": "Unauthorized or user not found"}), 404

    try:
        # LOGGING
        log = ActivityLog(
            actor_role=UserRole.ADMIN,
            actor_id=admin_id,
            action=f"Deleted user {user.email}",
            target_type="user",
            target_id=user.id
        )
        db.session.add(log)

        # Delete user (cascade deletes attendance + calls automatically)
        db.session.delete(user)
        db.session.commit()

        return jsonify({"message": "User deleted successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


# ----------------------------------------
# TOGGLE USER STATUS (BLOCK/UNBLOCK)
# ----------------------------------------
@admin_user_bp.route("/user/<int:user_id>/status", methods=["PUT"])
@jwt_required()
def toggle_user_status(user_id):
    if not admin_required():
        return jsonify({"error": "Admin only"}), 403

    admin_id = int(get_jwt_identity())

    # Check if user exists and belongs to this admin
    user = User.query.get(user_id)
    if not user or user.admin_id != admin_id:
        return jsonify({"error": "Unauthorized or user not found"}), 404

    try:
        # Toggle status
        user.is_active = not user.is_active
        db.session.commit()

        action = "Unblocked" if user.is_active else "Blocked"

        # LOGGING
        log = ActivityLog(
            actor_role=UserRole.ADMIN,
            actor_id=admin_id,
            action=f"{action} user {user.email}",
            target_type="user",
            target_id=user.id
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            "message": f"User {action.lower()} successfully",
            "is_active": user.is_active
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
