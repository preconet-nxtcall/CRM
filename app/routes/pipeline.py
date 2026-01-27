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
    # Statuses: New, Attempted, Converted, Interested, Follow-Up, Won, Lost
    # We group by status
    status_counts = (
        db.session.query(Lead.status, func.count(Lead.id))
        .filter(Lead.admin_id == admin_id)
        .group_by(Lead.status)
        .all()
    )
    
    # Normalize keys - Match frontend 7 statuses
    pipeline_data = {
        "New": 0,
        "Attempted": 0,
        "Converted": 0,
        "Interested": 0,
        "Follow-Up": 0,
        "Won": 0,
        "Lost": 0
    }

    for status, count in status_counts:
        if not status: continue
        s_norm = status.title() # Ensure Title Case
        
        # Map statuses to our 7 core buckets
        if s_norm in pipeline_data:
            pipeline_data[s_norm] += count
            
        # 1. Attempted (map common call statuses)
        elif s_norm in ["Attempted", "Ringing", "Busy", "Not Reachable", "Switch Off", "Call Later", "Callback", "No Answer"]:
            pipeline_data["Attempted"] += count
            
        # 2. Converted (map contacted/connected statuses)
        elif s_norm in ["Converted", "Connected", "Contacted", "In Conversation"]:
            pipeline_data["Converted"] += count
            
        # 3. Interested
        elif s_norm in ["Interested", "Meeting Scheduled", "Demo Scheduled"]:
            pipeline_data["Interested"] += count
            
        # 4. Follow-Up
        elif s_norm in ["Follow-Up", "Follow Up"]:
            pipeline_data["Follow-Up"] += count
            
        # 5. Won (map closed/converted)
        elif s_norm in ["Won", "Closed"]:
            pipeline_data["Won"] += count
            
        # 6. Lost (map junk, not interested, etc.)
        elif s_norm in ["Lost", "Junk", "Wrong Number", "Invalid", "Not Interested", "Not Intersted"]:
            pipeline_data["Lost"] += count
            
        else:
            # Fallback to Attempted
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
    status_filter = request.args.get("status")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))

    query = Lead.query.filter_by(admin_id=admin_id)

    if status_filter and status_filter != "all":
        # Handle mapped statuses
        if status_filter == "Follow-Up":
             query = query.filter(Lead.status.in_(["Follow-Up", "Follow Up"]))
        elif status_filter == "Won":
             query = query.filter(Lead.status.in_(["Won", "Converted"]))
        elif status_filter == "Lost":
             query = query.filter(Lead.status.in_(["Lost", "Junk"]))
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
    Shows current month's data by default, but can view previous months.
    Query params: month (1-12), year (e.g., 2026)
    """
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    
    # Date filter: Get month and year from query params or use current month
    now = datetime.utcnow()
    target_month = request.args.get('month', now.month, type=int)
    target_year = request.args.get('year', now.year, type=int)
    
    # Validate month
    if target_month < 1 or target_month > 12:
        return jsonify({"error": "Invalid month. Must be between 1 and 12"}), 400
    
    # Calculate month start and end
    month_start = datetime(target_year, target_month, 1, 0, 0, 0)
    
    # Calculate next month for end date
    if target_month == 12:
        month_end = datetime(target_year + 1, 1, 1, 0, 0, 0)
    else:
        month_end = datetime(target_year, target_month + 1, 1, 0, 0, 0)
    
    users = User.query.filter_by(admin_id=admin_id).all()
    user_ids = [u.id for u in users]
    
    # Aggregates - Selected Month Only
    # 1. Total Calls per Agent (Selected Month)
    calls_counts = db.session.query(CallHistory.user_id, func.count(CallHistory.id)).filter(
        CallHistory.user_id.in_(user_ids),
        CallHistory.timestamp >= month_start,
        CallHistory.timestamp < month_end
    ).group_by(CallHistory.user_id).all()
    calls_map = {uid: count for uid, count in calls_counts}

    # 2. Leads Assigned per Agent (Selected Month)
    leads_counts = db.session.query(Lead.assigned_to, func.count(Lead.id)).filter(
        Lead.admin_id == admin_id,
        Lead.created_at >= month_start,
        Lead.created_at < month_end
    ).group_by(Lead.assigned_to).all()
    leads_map = {uid: count for uid, count in leads_counts}

    # 3. Converted/Won Leads per Agent (Selected Month)
    won_counts = db.session.query(Lead.assigned_to, func.count(Lead.id)).filter(
        Lead.admin_id == admin_id,
        Lead.status.in_(["Converted", "Won"]),
        Lead.updated_at >= month_start,
        Lead.updated_at < month_end
    ).group_by(Lead.assigned_to).all()
    won_map = {uid: count for uid, count in won_counts}

    data = []
    for u in users:
        data.append({
            "name": u.name,
            "assigned_leads": leads_map.get(u.id, 0),
            "calls_made": calls_map.get(u.id, 0),
            "connected_calls": 0, # Placeholder, needs complex logic or duration filter
            "closed_leads": won_map.get(u.id, 0)
        })
    
    # Sort by Closed Leads desc
    data.sort(key=lambda x: x['closed_leads'], reverse=True)

    return jsonify({
        "agents": data,
        "month": target_month,
        "year": target_year
    }), 200
