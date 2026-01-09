from flask import Blueprint, request, jsonify, current_app
from ..models import db, User, Attendance, AppUsage, Admin
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from app.auth_helpers import get_authorized_user

bp = Blueprint("app_usage", __name__, url_prefix="/api")

# ---------------------------
# GET /api/app_usage/ping
# Connectivity Check
# ---------------------------
@bp.route("/app_usage/ping", methods=["GET"])
def ping_app_usage():
    return jsonify({"status": "ok", "message": "App Usage Blueprint Loaded"}), 200

# ---------------------------
# POST /api/app_usage/sync
# Syncs usage data from Mobile App
# ---------------------------
@bp.route("/app_usage/sync", methods=["POST"])
@jwt_required()
def sync_app_usage():
    try:
        data = request.get_json()
        
        # Verify Mobile User Authorization
        user, err_resp = get_authorized_user()
        if err_resp:
            return err_resp
            
        required = ["attendance_id", "start_time", "end_time", "total_usage_seconds", "apps"]
        for r in required:
            if r not in data:
                return jsonify({"error": f"Missing field: {r}"}), 400
                
        # Validate Attendance
        attendance_id = data["attendance_id"]
        
        # 1. Try lookup by PK (Server ID)
        attendance = Attendance.query.get(attendance_id)
        
        # 2. If not found, try lookup by external_id (Mobile ID)
        if not attendance:
             attendance = Attendance.query.filter_by(external_id=str(attendance_id)).first()
        
        if not attendance:
             return jsonify({"error": "Attendance record not found"}), 404
             
        if attendance.user_id != user.id:
            return jsonify({"error": "Unauthorized assignment"}), 403
            
        # Ensure we use the Server ID for the foreign key
        real_attendance_id = attendance.id
            
        # Parse Times
        # Timestamps are likely milliseconds from simple json
        start_ts = data["start_time"]
        end_ts = data["end_time"]
        
        # Helper to convert ms timestamp to datetime
        def to_dt(ts):
             return datetime.utcfromtimestamp(ts / 1000.0) + timedelta(hours=5, minutes=30)
             
        start_dt = to_dt(start_ts)
        end_dt = to_dt(end_ts)
        
        # Create App Usage Record
        new_record = AppUsage(
            attendance_id=real_attendance_id,
            user_id=user.id,
            start_time=start_dt,
            end_time=end_dt,
            total_usage_seconds=int(data["total_usage_seconds"]),
            apps_data=data["apps"] # JSON list
        )
        # Check for existing App Usage record for this attendance session
        existing_usage = AppUsage.query.filter_by(attendance_id=real_attendance_id).first()
        
        if existing_usage:
            # UPDATE existing record
            existing_usage.start_time = start_dt
            existing_usage.end_time = end_dt
            existing_usage.total_usage_seconds = int(data["total_usage_seconds"])
            existing_usage.apps_data = data["apps"]
            # Option: update sync time or anything else
            
            return jsonify({"success": True, "message": "App usage updated", "id": existing_usage.id}), 200
        else:
            # CREATE new record
            new_record = AppUsage(
                attendance_id=real_attendance_id,
                user_id=user.id,
                start_time=start_dt,
                end_time=end_dt,
                total_usage_seconds=int(data["total_usage_seconds"]),
                apps_data=data["apps"] # JSON list
            )
            
            db.session.add(new_record)
            db.session.commit()
            
            return jsonify({"success": True, "message": "App usage synced", "id": new_record.id}), 201
            
    except Exception as e:
        current_app.logger.exception("App Usage Sync Failed")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ---------------------------
# GET /api/admin/app_usage_records
# For Admin Dashboard
# ---------------------------
@bp.route("/admin/app_usage_records", methods=["GET"])
@jwt_required()
def get_admin_app_usage_records():
    try:
        admin_id = int(get_jwt_identity())
        admin = Admin.query.get(admin_id)
        if not admin:
            return jsonify({"error": "Unauthorized"}), 401
            
        # Filters
        user_id = request.args.get("user_id")
        date_filter = request.args.get("filter", "today") # today, yesterday
        
        query = AppUsage.query.join(User).filter(User.admin_id == admin_id)
        
        if user_id and user_id != "all":
            query = query.filter(AppUsage.user_id == int(user_id))
            
        # Date Filter (on start_time)
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        
        custom_date = request.args.get("date")
        
        if custom_date:
            try:
                # Parse YYYY-MM-DD
                dt = datetime.strptime(custom_date, '%Y-%m-%d')
                start_of_day = dt
                end_of_day = dt + timedelta(days=1)
                query = query.filter(AppUsage.start_time >= start_of_day, AppUsage.start_time < end_of_day)
            except ValueError:
                pass # Ignore invalid date format
        elif date_filter == "today":
            query = query.filter(AppUsage.start_time >= today_start)
        elif date_filter == "yesterday":
            yesterday_start = today_start - timedelta(days=1)
            query = query.filter(AppUsage.start_time >= yesterday_start, AppUsage.start_time < today_start)
            
        # Debug Print
        print(f"Admin AppUsage Query: {query}")
            
        # Sort desc
        records = query.order_by(AppUsage.created_at.desc()).all()
        
        results = []
        for r in records:
            d = r.to_dict()
            # Add user name explicitly if not in helper
            d["user_name"] = r.user.name
            results.append(d)
            
        return jsonify(results), 200
        
    except Exception as e:
        current_app.logger.exception("Admin fetch app usage failed")
        return jsonify({"error": str(e)}), 500
