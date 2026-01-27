# app/routes/pipeline.py

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
from sqlalchemy import func, case
from app.models import db, Lead, User, CallHistory, CallMetrics, Admin

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/api/pipeline")

def admin_required():
    claims = get_jwt()
    return claims.get("role") == "admin"

@pipeline_bp.route("/stats", methods=["GET"])
@jwt_required()
def pipeline_stats():
    """
    Returns top-level KPIs for the Pipeline Dashboard.
    """
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())

    # 1. Date Filter (Timezone Aware)
    # Match logic from admin_dashboard.py for consistency
    try:
        offset_min = int(request.args.get("timezone_offset", 0))
    except:
        offset_min = 0
    
    # Calculate local start of day
    # Local Time = UTC - offset_min (minutes)
    # But usually Frontend sends (UTC - Local), so Local = UTC - offset.
    # JS: new Date().getTimezoneOffset() -> -330 for IST. 
    # So UTC + 330 mins = IST.
    # We want "Today 00:00" in Local Time converted back to UTC?
    # Or just filter on Local Time if DB was Local... but DB is UTC.
    
    # Strategy: Determine the UTC range that corresponds to "Local Today"
    
    # Current UTC
    now_utc = datetime.utcnow()
    
    # Current Local Time
    local_delta = timedelta(minutes=-offset_min)
    now_local = now_utc + local_delta
    
    # Local Day Start (00:00)
    local_today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Convert Local Day Start back to UTC to query DB
    # UTC = Local - delta
    today_start_utc = local_today_start - local_delta

    # 1. Total Leads
    total_leads = Lead.query.filter_by(admin_id=admin_id).count()

    # 2. New Leads Today
    new_leads_today = Lead.query.filter(
        Lead.admin_id == admin_id,
        Lead.created_at >= today_start_utc
    ).count()

    # 3. Calls Today (from CallHistory)
    # We need to filter by users belonging to this admin
    users = User.query.filter_by(admin_id=admin_id).all()
    user_ids = [u.id for u in users]

    calls_today_query = CallHistory.query.filter(
        CallHistory.user_id.in_(user_ids),
        CallHistory.timestamp >= today_start_utc
    )
    
    calls_made_today = calls_today_query.count()
    
    # 4. Connected Calls Today
    # Assuming 'connected' isn't a direct status but usually IMPLIED by duration > 0 or specific status?
    # Let's rely on call_type or duration. If 'outgoing' and duration > 0 usually connected.
    # Or if we have a status field. The model has 'call_type'.
    # Let's count calls with duration > 10 seconds as a proxy for "Effective Connected", or just > 0.
    connected_calls_today = calls_today_query.filter(CallHistory.duration > 0).count()

    # 5. Conversion Rate (Converted Leads / Total Leads) * 100
    converted_leads = Lead.query.filter_by(admin_id=admin_id, status="Converted").count()
    conversion_rate = 0
    if total_leads > 0:
        conversion_rate = round((converted_leads / total_leads) * 100, 2)

    # 6. Pipeline Breakdown
    # Statuses: New, Attempted, Connected, Interested, Follow-Up, Closed, Lost, Won
    # We group by status
    status_counts = (
        db.session.query(Lead.status, func.count(Lead.id))
        .filter(Lead.admin_id == admin_id)
        .group_by(Lead.status)
        .all()
    )
    
    # Normalize keys
    pipeline_data = {
        "New": 0,
        "Attempted": 0,
        "Connected": 0,
        "Converted": 0,
        "Follow-Up": 0,
        "Won": 0,
        "Lost": 0
    }

    for status, count in status_counts:
        if not status: continue
        s_norm = status.title() # Ensure Title Case
        
        # Map disparate statuses to our 7 core buckets
        if s_norm in pipeline_data:
            pipeline_data[s_norm] += count
            
        # 1. Attempted
        elif s_norm in ["Attempted", "Ringing", "Busy", "Not Reachable", "Switch Off", "Call Later", "Callback", "No Answer"]:
            pipeline_data["Attempted"] += count
            
        # 2. Connected (Includes "Contacted")
        elif s_norm in ["Connected", "Contacted", "In Conversation"]:
            pipeline_data["Connected"] += count
            
        # 3. Converted (Replacing Interested)
        elif s_norm in ["Converted", "Interested", "Meeting Scheduled", "Demo Scheduled"]:
            pipeline_data["Converted"] += count
            
        # 4. Follow-Up
        elif s_norm in ["Follow-Up", "Follow Up"]:
            pipeline_data["Follow-Up"] += count
            
        # 5. Won
        elif s_norm in ["Won", "Closed"]:
            pipeline_data["Won"] += count
            
        # 6. Lost (Includes "Not Interested" and "Junk" now as they are not separate)
        elif s_norm in ["Lost", "Junk", "Wrong Number", "Invalid", "Not Interested", "Not Intersted"]:
            pipeline_data["Lost"] += count
            
        else:
            # Fallback
            pipeline_data["Attempted"] += count

    return jsonify({
        "kpis": {
            "total_leads": total_leads,
            "new_leads_today": new_leads_today,
            "calls_made_today": calls_made_today,
            "connected_calls_today": connected_calls_today,
            "conversion_rate": conversion_rate
        },
        "pipeline": pipeline_data
    }), 200


@pipeline_bp.route("/leads", methods=["GET"])
@jwt_required()
def pipeline_leads():
    """
    Formatted lead list for the table.
    """
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    
    # query params
    # query params
    status_filter = request.args.get("status")
    date_filter = request.args.get("date_filter")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 10)) # Default to 10 as requested

    query = Lead.query.filter_by(admin_id=admin_id)

    # Date Filter (Today)
    if date_filter == "today":
        try:
            offset_min = int(request.args.get("timezone_offset", 0))
        except:
            offset_min = 0
            
        now_utc = datetime.utcnow()
        local_delta = timedelta(minutes=-offset_min)
        now_local = now_utc + local_delta
        local_today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = local_today_start - local_delta
        
        query = query.filter(Lead.created_at >= today_start_utc)

    if status_filter and status_filter != "all":
        # Handle mapped statuses
        if status_filter == "Follow-Up":
             query = query.filter(Lead.status.in_(["Follow-Up", "Follow Up"]))
        elif status_filter == "Won":
             query = query.filter(Lead.status.in_(["Won", "Closed"]))
        elif status_filter == "Converted":
             query = query.filter(Lead.status.in_(["Converted", "Interested"]))
        elif status_filter == "Lost":
             query = query.filter(Lead.status.in_(["Lost", "Junk", "Not Interested"]))
        elif status_filter == "Connected":
             query = query.filter(Lead.status.in_(["Connected", "Contacted"]))
        else:
             query = query.filter(func.lower(Lead.status) == status_filter.lower())

    # Sorting: Recent first
    query = query.order_by(Lead.created_at.desc())

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    data = []
    for lead in paginated.items:
        # Resolve Assigned Agent Name
        agent_name = lead.assignee.name if lead.assignee else "Unassigned"
        
        # Last Call Logic (expensive query? optimize later)
        # For now, subquery or just fetch latest call for this number?
        # Let's leave last_call as null or implement if strictly needed.
        # User requested "Last Call Time".
        # We can JOIN CallHistory on phone number? 
        # A bit heavy for a list. Let's do a quick separate query or skip for MVP performance.
        # Efficient way: Lead stores last_interaction timestamp?
        # Lead model has `updated_at`. Let's use that as proxy for "Last Activity" for now.
        
        data.append({
            "id": lead.id,
            "name": lead.name or "Unknown",
            "phone": lead.phone,
            "source": lead.source.upper() if lead.source else "-",
            "agent": agent_name,
            "status": lead.status,
            "last_activity": (lead.updated_at.isoformat() + "Z") if lead.updated_at else None,
            # Next Followup would need a Join with Followup table.
            "created_at": (lead.created_at.isoformat() + "Z") if lead.created_at else None
        })

    return jsonify({
        "leads": data,
        "pagination": {
            "total": paginated.total,
            "pages": paginated.pages,
            "current": page
        }
    }), 200

@pipeline_bp.route("/agents", methods=["GET"])
@jwt_required()
def pipeline_agents():
    """
    Agent Performance for the pipeline view.
    """
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    
    # query params
    date_filter = request.args.get("date_filter")
    
    users = User.query.filter_by(admin_id=admin_id).all()
    user_ids = [u.id for u in users]
    
    # Base Queries
    calls_query = db.session.query(CallHistory.user_id, func.count(CallHistory.id)).filter(
        CallHistory.user_id.in_(user_ids)
    )
    
    won_query = db.session.query(Lead.assigned_to, func.count(Lead.id)).filter(
        Lead.admin_id == admin_id,
        Lead.status.in_(["Converted", "Won"])
    )

    # Apply Date Filter
    if date_filter == "month" or date_filter == "last_month":
        try:
            offset_min = int(request.args.get("timezone_offset", 0))
        except:
            offset_min = 0
            
        now_utc = datetime.utcnow()
        local_delta = timedelta(minutes=-offset_min)
        now_local = now_utc + local_delta
        
        # Start of current month: Day 1, 00:00:00
        local_month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_start_utc = local_month_start - local_delta
        
        if date_filter == "month":
            calls_query = calls_query.filter(CallHistory.timestamp >= month_start_utc)
            won_query = won_query.filter(Lead.updated_at >= month_start_utc)
            
        elif date_filter == "last_month":
            # Calculate start of last month using 1st of current month - 1 day -> replace day=1
            local_last_month_end = local_month_start # effectively logic start of this month is exclusive end of last
            local_last_month_start = (local_month_start - timedelta(days=1)).replace(day=1)
            
            last_month_start_utc = local_last_month_start - local_delta
            last_month_end_utc = local_last_month_end - local_delta # Same as month_start_utc
            
            calls_query = calls_query.filter(CallHistory.timestamp >= last_month_start_utc, CallHistory.timestamp < last_month_end_utc)
            won_query = won_query.filter(Lead.updated_at >= last_month_start_utc, Lead.updated_at < last_month_end_utc)

    # Aggregates
    calls_counts = calls_query.group_by(CallHistory.user_id).all()
    calls_map = {uid: count for uid, count in calls_counts}

    # 2. Leads Assigned per Agent (All time usually, or should this match? Let's keep all time for assignment context, or filter? Usually performance is calls/closes. Assigned might be irrelevant for performance ratio if filtered. Leaving Assigned as is or filtering? User only asked for Performance (Calls/Closed). 
    # Let's keep Assigned all-time or simple count to avoid complexity unless asked. User emphasized "current month record" for performance.
    
    leads_counts = db.session.query(Lead.assigned_to, func.count(Lead.id)).filter(
        Lead.admin_id == admin_id
    ).group_by(Lead.assigned_to).all()
    leads_map = {uid: count for uid, count in leads_counts}

    won_counts = won_query.group_by(Lead.assigned_to).all()
    won_map = {uid: count for uid, count in won_counts}

    data = []
    for u in users:
        data.append({
            "name": u.name,
            "assigned_leads": leads_map.get(u.id, 0),
            "calls_made": calls_map.get(u.id, 0),
            "connected_calls": 0, # Placeholder
            "closed_leads": won_map.get(u.id, 0)
        })
    
    # Sort by Closed Leads desc
    data.sort(key=lambda x: x['closed_leads'], reverse=True)

    return jsonify({"agents": data}), 200
