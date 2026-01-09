# app/routes/call_analytics.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.auth_helpers import get_authorized_user
from datetime import datetime, timedelta
from sqlalchemy import func
from app.models import db, User, CallHistory
from app.models import db


bp = Blueprint("call_analytics", __name__, url_prefix="/api/call-analytics")


# ===============================================================
# 1️⃣  SYNC ANALYTICS  (POST)
#     Saves last_sync + returns analytics summary
# ===============================================================
@bp.route("/sync", methods=["POST"])
@jwt_required()
def sync_analytics():
    try:
        user, err_resp = get_authorized_user()
        if err_resp:
            return err_resp
        user_id = user.id

        # ---- Total Calls ----
        total_calls = CallHistory.query.filter_by(user_id=user_id).count()

        # ---- Call Type Summary ----
        call_types = (
            db.session.query(
                CallHistory.call_type,
                func.count(CallHistory.id)
            )
            .filter(CallHistory.user_id == user_id)
            .group_by(CallHistory.call_type)
            .all()
        )

        call_type_summary = {ctype: count for ctype, count in call_types}

        # ---- Total Call Duration ----
        total_duration = (
            db.session.query(func.coalesce(func.sum(CallHistory.duration), 0))
            .filter(CallHistory.user_id == user_id)
            .scalar()
            or 0
        )

        # ---- Update Last Sync ----
        user.last_sync = datetime.utcnow()
        db.session.commit()

        # ---- Final Response ----
        return jsonify({
            "message": "Analytics synced successfully",
            "user_id": user_id,
            "total_calls": total_calls,
            "call_types": call_type_summary,
            "total_duration_seconds": total_duration,
            "last_sync": user.last_sync.isoformat()
        }), 200

    except Exception as e:
        current_app.logger.exception("SYNC ERROR")
        return jsonify({"error": str(e)}), 400


# ===============================================================
# 2️⃣  GET ANALYTICS (GET)
#     Returns full analytics with trends and KPIs
# ===============================================================
@bp.route("", methods=["GET"])
@jwt_required()
def get_analytics():
    try:
        user, err_resp = get_authorized_user()
        if err_resp:
            return err_resp
        user_id = user.id

        # Base query
        base_query = CallHistory.query.filter_by(user_id=user_id)

        # ---- KPIs ----
        total_calls = base_query.count()
        
        # Answered calls (duration > 0)
        total_answered = base_query.filter(CallHistory.duration > 0).count()

        # Call Types
        incoming = base_query.filter(func.lower(CallHistory.call_type) == "incoming").count()
        outgoing = base_query.filter(func.lower(CallHistory.call_type) == "outgoing").count()
        missed = base_query.filter(func.lower(CallHistory.call_type) == "missed").count()
        rejected = base_query.filter(func.lower(CallHistory.call_type) == "rejected").count()

        # Durations
        total_duration = db.session.query(func.coalesce(func.sum(CallHistory.duration), 0)).filter(CallHistory.user_id == user_id).scalar() or 0
        
        # Avg Durations
        avg_outbound_duration = 0
        if outgoing > 0:
            outbound_duration_sum = db.session.query(func.coalesce(func.sum(CallHistory.duration), 0)).filter(CallHistory.user_id == user_id, func.lower(CallHistory.call_type) == "outgoing").scalar() or 0
            avg_outbound_duration = int(outbound_duration_sum / outgoing)

        avg_inbound_duration = 0
        if incoming > 0:
            inbound_duration_sum = db.session.query(func.coalesce(func.sum(CallHistory.duration), 0)).filter(CallHistory.user_id == user_id, func.lower(CallHistory.call_type) == "incoming").scalar() or 0
            avg_inbound_duration = int(inbound_duration_sum / incoming)

        # ---- Trends (Last 7 Days) ----
        today = datetime.utcnow().date()
        dates = [today - timedelta(days=i) for i in range(6, -1, -1)]
        
        activity_trend = []
        duration_trend = []

        for d in dates:
            # Start and end of day
            start_dt = datetime.combine(d, datetime.min.time())
            end_dt = datetime.combine(d, datetime.max.time())
            
            # Daily Count
            count = base_query.filter(CallHistory.timestamp >= start_dt, CallHistory.timestamp <= end_dt).count()
            activity_trend.append({"date": d.isoformat(), "count": count})

            # Daily Duration
            dur = db.session.query(func.coalesce(func.sum(CallHistory.duration), 0)).filter(CallHistory.user_id == user_id, CallHistory.timestamp >= start_dt, CallHistory.timestamp <= end_dt).scalar() or 0
            duration_trend.append({"date": d.isoformat(), "duration": dur})

        # ---- Final Response ----
        return jsonify({
            "user_id": user_id,
            "kpis": {
                "total_calls": total_calls,
                "total_duration": total_duration,
                "total_answered": total_answered,
                "incoming": incoming,
                "outgoing": outgoing,
                "missed": missed,
                "rejected": rejected,
                "avg_outbound_duration": avg_outbound_duration,
                "avg_inbound_duration": avg_inbound_duration
            },
            "trends": {
                "activity": activity_trend,
                "duration": duration_trend
            },
            "last_sync": user.last_sync.isoformat() if user.last_sync else None
        }), 200

    except Exception as e:
        current_app.logger.exception("GET ANALYTICS ERROR")
        return jsonify({"error": str(e)}), 400
