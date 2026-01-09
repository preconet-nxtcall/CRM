from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import User, CallHistory

bp = Blueprint("admin_sync", __name__, url_prefix="/api/admin")

@bp.route("/sync-summary", methods=["GET"])
@jwt_required()
def sync_summary():
    if get_jwt().get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    admin_id = int(get_jwt_identity())

    users = User.query.filter_by(admin_id=admin_id).all()

    result = []
    for u in users:
        # Count only non-duplicate calls if needed, but with unique constraint, count() is accurate
        total_calls = CallHistory.query.filter_by(user_id=u.id).count()
        total_attendance = Attendance.query.filter_by(user_id=u.id).count()

        result.append({
            "user_id": u.id,
            "user_name": u.name,
            "last_sync": u.last_sync.isoformat() if u.last_sync else None,
            "total_synced_calls": total_calls,
            "total_attendance_records": total_attendance
        })

    return jsonify({"users": result}), 200
