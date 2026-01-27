# app/routes/admin_dashboard.py

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
from sqlalchemy import func
from app.models import db

from app.models import User, Admin, Attendance, CallHistory, ActivityLog

admin_dashboard_bp = Blueprint("admin_dashboard", __name__, url_prefix="/api/admin")


# ---------------------------
# HELPERS
# ---------------------------
def admin_required():
    claims = get_jwt()
    return claims.get("role") == "admin"


def iso(dt):
    if not dt:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


# =========================================================
# 1️⃣ DASHBOARD STATS (TOP CARDS)
# =========================================================
@admin_dashboard_bp.route("/dashboard-stats", methods=["GET"])
@jwt_required()
def dashboard_stats():
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    admin = Admin.query.get(admin_id)

    if not admin:
        return jsonify({"error": "Admin account not found"}), 404

    users = User.query.filter_by(admin_id=admin_id).all()
    total = len(users)
    active = sum(1 for u in users if u.is_active)
    synced = sum(1 for u in users if u.last_sync)

    # Handle None values in performance_score safely
    total_score = sum((u.performance_score or 0.0) for u in users)
    avg_perf = round(total_score / total, 2) if total else 0

    # Calculate daily call trend (last 7 days)
    # OPTIMIZED: Use SQL Aggregation instead of Python Loop
    # This prevents loading millions of rows into memory.
    
    daily_counts = []
    day_labels = []
    
    # Get timezone offset
    try:
        offset_min = int(request.args.get("timezone_offset", 0))
    except:
        offset_min = 0
            
    # Local Time Calculation
    # Local = UTC - (offset_min)
    # If offset_min = -330 (IST), Local = UTC + 330m
    local_delta = timedelta(minutes=-offset_min)
    now_local = datetime.utcnow() + local_delta
    
    # We want last 7 days including today
    start_date_local = now_local.date() - timedelta(days=6)
    
    # Convert start/end range back to UTC for efficient index usage filter
    # Range: from start_of_first_day_local -> end_of_today_local
    start_dt_local = datetime.combine(start_date_local, datetime.min.time())
    end_dt_local = datetime.combine(now_local.date(), datetime.max.time())
    
    start_dt_utc = start_dt_local - local_delta
    end_dt_utc = end_dt_local - local_delta

    # Query Aggregation
    # We group by the effective local date. 
    # Logic: date(timestamp + local_delta)
    # Note: SQLAlchemy + Postgres supports timestamp + timedelta = timestamp + interval
    
    trend_data = (
        db.session.query(
            func.date(CallHistory.timestamp + local_delta).label("day"),
            func.count(CallHistory.id)
        )
        .join(User, CallHistory.user_id == User.id)
        .filter(User.admin_id == admin_id)
        .filter(CallHistory.timestamp >= start_dt_utc)
        .filter(CallHistory.timestamp <= end_dt_utc)
        .group_by(func.date(CallHistory.timestamp + local_delta))
        .all()
    )
    
    # Map results
    # trend_data is list of (date_obj, count)
    data_map = {str(r[0]): r[1] for r in trend_data if r[0] is not None}
    
    # Build result arrays (fill zeros)
    for i in range(6, -1, -1):
        d = (now_local - timedelta(days=i)).date()
        d_str = str(d)
        
        count = data_map.get(d_str, 0)
        daily_counts.append(count)
        day_labels.append(d.strftime("%a"))

    return jsonify({
        "stats": {
            "total_users": total,
            "active_users": active,
            "expired_users": 0,
            "user_limit": admin.user_limit,
            "remaining_slots": admin.user_limit - total,
            "synced_users": synced,
            "sync_rate": round((synced / total) * 100, 2) if total else 0,
            "avg_performance": avg_perf,
            "call_trend": {
                "labels": day_labels,
                "data": daily_counts
            },
            "day_labels": day_labels,  # kept for legacy if needed
            "admin_name": admin.name,
            "admin_email": admin.email
        }
    }), 200


# =========================================================
# 2️⃣ FIXED — RECENT SYNC LAST 10 USERS
# =========================================================
@admin_dashboard_bp.route("/recent-sync", methods=["GET"])
@jwt_required()
def recent_sync():
    try:
        if not admin_required():
            return jsonify({"error": "Admin only"}), 403

        admin_id = int(get_jwt_identity())

        # Removed nullslast() to be safe across DB versions
        users = (
            User.query
            .filter(User.admin_id == admin_id)
            .order_by(User.last_sync.desc())
            .limit(10)
            .all()
        )

        print("="*80, flush=True)
        print(f"[RECENT_SYNC] Endpoint called at {datetime.utcnow()}", flush=True)
        print(f"[RECENT_SYNC] Found {len(users)} users", flush=True)
        print("="*80, flush=True)

        # Strict check as requested: "today date syncronize means online"
        return jsonify({
            "recent_sync": [
                {
                    "id": u.id,
                    "name": u.name,
                    "email": u.email or "-",
                    "phone": u.phone or "-",
                    "is_active": u.is_active,
                    "last_sync": iso(u.last_sync),
                    "is_online": check_online_status(u.last_sync)
                }
                for u in users
            ]
        }), 200
    except Exception as e:
        print(f"Error in recent_sync: {e}")
        return jsonify({"error": str(e)}), 400

def check_online_status(dt):
    """Check if user is online based on sync date matching today (IST)"""
    if not dt:
        return False
    try:
        # Get today's date in IST
        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        today_ist = ist_now.date()
        
        print(f"[SYNC DEBUG] Input dt: {dt}, type: {type(dt)}", flush=True)
        
        # Handle the sync datetime
        sync_dt = dt
        if isinstance(dt, str):
            sync_dt = datetime.fromisoformat(str(dt).replace('Z', '+00:00'))
            print(f"[SYNC DEBUG] Parsed from string: {sync_dt}", flush=True)
        
        # CRITICAL: Convert sync time from UTC to IST before extracting date
        # The database stores UTC time, but we need to compare IST dates
        if hasattr(sync_dt, 'date'):
            print(f"[SYNC DEBUG] UTC datetime: {sync_dt}", flush=True)
            sync_dt_ist = sync_dt + timedelta(hours=5, minutes=30)
            print(f"[SYNC DEBUG] IST datetime: {sync_dt_ist}", flush=True)
            sync_date = sync_dt_ist.date()
            print(f"[SYNC DEBUG] IST date extracted: {sync_date}", flush=True)
        else:
            sync_date = sync_dt
            print(f"[SYNC DEBUG] Direct date (no conversion): {sync_date}", flush=True)
        
        # Simple comparison: does the sync date match today?
        is_online = (sync_date == today_ist)
        
        print(f"[SYNC DEBUG] FINAL: sync_date={sync_date} == today_ist={today_ist} ? {is_online}", flush=True)
        return is_online
        
    except Exception as e:
        print(f"ERROR in check_online_status: {e}, dt={dt}, type={type(dt)}")
        return False

# ... inside route ...
# "is_online": is_same_day(u.last_sync)


# =========================================================
# 3️⃣ USER ACTIVITY LOGS (latest 20)
# =========================================================
@admin_dashboard_bp.route("/user-logs", methods=["GET"])
@jwt_required()
def user_logs():
    try:
        if not admin_required():
            return jsonify({"error": "Admin only"}), 403

        admin_id = int(get_jwt_identity())

        # Define "today" in UTC
        now_utc = datetime.utcnow()
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        # Fetch TODAY's attendance events only
        logs_query = db.session.query(Attendance, User).join(User).filter(
            User.admin_id == admin_id,
            Attendance.check_in >= today_start  # Only today's records
        ).order_by(Attendance.created_at.desc()).limit(10).all()

        logs = []
        for att, user in logs_query:
            # Determine status based on check-in/check-out
            if att.check_in and not att.check_out:
                status = "Active"
                is_active = True
            else:
                status = "Inactive"
                is_active = False
                
            logs.append({
                "user_name": user.name,
                "action": f"Status: {status}",
                "timestamp": iso(att.check_in),
                "is_active": is_active
            })

        return jsonify({
            "logs": logs
        }), 200
    except Exception as e:
        print(f"Error in user_logs: {e}")
        return jsonify({"error": str(e)}), 400


# =========================================================
# 4️⃣ ADMIN — ALL ATTENDANCE
# =========================================================
@admin_dashboard_bp.route("/attendance", methods=["GET"])
@jwt_required()
def admin_attendance():
    if not admin_required():
        return jsonify({"error": "Admin only"}), 403

    admin_id = int(get_jwt_identity())

    records = (
        db.session.query(Attendance, User)
        .join(User, Attendance.user_id == User.id)
        .filter(User.admin_id == admin_id)
        .order_by(Attendance.created_at.desc())
        .all()
    )

    return jsonify({
        "attendance": [
            {
                "id": a.id,
                "user_name": u.name,
                "check_in": iso(a.check_in),
                "check_out": iso(a.check_out),
                "address": a.address,
                "latitude": a.latitude,
                "longitude": a.longitude,
                "status": a.status,
            }
            for a, u in records
        ]
    }), 200


# =========================================================
# 5️⃣ ADMIN — SIMPLE CALL HISTORY (LATEST 200)
# =========================================================
@admin_dashboard_bp.route("/call-history", methods=["GET"])
@jwt_required()
def admin_call_history():
    if not admin_required():
        return jsonify({"error": "Admin only"}), 403

    admin_id = int(get_jwt_identity())

    users = User.query.filter_by(admin_id=admin_id).all()
    user_ids = [u.id for u in users]

    calls = (
        db.session.query(CallHistory, User)
        .join(User, User.id == CallHistory.user_id)
        .filter(CallHistory.user_id.in_(user_ids))
        .order_by(CallHistory.timestamp.desc())
        .limit(200)
        .all()
    )

    return jsonify({
        "call_history": [
            {
                "id": c.id,
                "user_id": u.id,
                "user_name": u.name,
                "phone_number": c.phone_number,
                "call_type": c.call_type,
                "duration": c.duration,
                "timestamp": iso(c.timestamp),
                "created_at": iso(c.created_at),
            }
            for c, u in calls
        ]
    }), 200


# =========================================================
# 6️⃣ ADMIN — CALL ANALYTICS (Frontend uses new API)
# =========================================================
# NOTE:
# This file now keeps only the LATEST-CALLS version
# The real analytics is handled in:
#   app/routes/admin_call_analytics.py
# which you already fixed and connected JS to.

