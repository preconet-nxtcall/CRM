# app/routes/pipeline.py

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_
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
    now_utc = datetime.utcnow()
    local_delta = timedelta(minutes=-offset_min)
    now_local = now_utc + local_delta
    local_today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = local_today_start - local_delta

    # Handle Date Filter for Funnel/Stats
    date_filter = request.args.get("date_filter", "all")
    filter_start_utc = None
    filter_end_utc = None

    if date_filter == 'today':
        filter_start_utc = today_start_utc
        # End is implicit (create_at >= start)
    elif date_filter == 'week':
        # Start of week (Monday)
        days_since_monday = local_today_start.weekday()
        week_start_local = local_today_start - timedelta(days=days_since_monday)
        filter_start_utc = week_start_local - local_delta
    elif date_filter == 'month':
        # Start of month
        month_start_local = local_today_start.replace(day=1)
        filter_start_utc = month_start_local - local_delta

    # 1. Total Leads (Global or Filtered?)
    # Usually Total Leads KPI is ALL TIME unless filtered
    # If filtered, show count in range.
    lead_query = Lead.query.filter_by(admin_id=admin_id)
    if filter_start_utc:
        lead_query = lead_query.filter(Lead.created_at >= filter_start_utc)
    
    total_leads = lead_query.count()

    # 2. New Leads Today (Always Today for this specific KPI)
    new_leads_today = Lead.query.filter(
        Lead.admin_id == admin_id,
        Lead.created_at >= today_start_utc
    ).count()

    # 3. Calls Today (Always Today for this specific KPI)
    users = User.query.filter_by(admin_id=admin_id).all()
    user_ids = [u.id for u in users]

    calls_today_query = CallHistory.query.filter(
        CallHistory.user_id.in_(user_ids),
        CallHistory.timestamp >= today_start_utc
    )
    
    calls_made_today = calls_today_query.count()
    connected_calls_today = calls_today_query.filter(CallHistory.duration > 0).count()

    # 5. Conversion Rate (Converted Leads / Total Leads in Filter) * 100
    converted_query = Lead.query.filter(
        Lead.admin_id == admin_id, 
        Lead.status.in_(["Converted", "Won", "Closed"])
    )
    if filter_start_utc:
        converted_query = converted_query.filter(Lead.created_at >= filter_start_utc)
    
    converted_leads = converted_query.count()
    conversion_rate = 0
    if total_leads > 0:
        conversion_rate = round((converted_leads / total_leads) * 100, 2)

    # 6. Pipeline Breakdown
    # Statuses based on Filter
    pipeline_query = db.session.query(Lead.status, func.count(Lead.id)).filter(Lead.admin_id == admin_id)
    
    if filter_start_utc:
        pipeline_query = pipeline_query.filter(Lead.created_at >= filter_start_utc)
        
    status_counts = (
        pipeline_query
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
            
        # 1. Attempted (map common call statuses + Connected/Contacted)
        # Removed "Call Later", "Callback" -> Moved to Follow-Up
        elif s_norm in ["Attempted", "Ringing", "Busy", "Not Reachable", "Switch Off", "No Answer", "Connected", "Contacted", "In Conversation"]:
            pipeline_data["Attempted"] += count
            
        # 2. Converted (Explicit conversions only)
        elif s_norm in ["Converted"]:
            pipeline_data["Converted"] += count
            
        # 3. Interested
        elif s_norm in ["Interested", "Meeting Scheduled", "Demo Scheduled"]:
            pipeline_data["Interested"] += count
            
        # 4. Follow-Up
        elif s_norm in ["Follow-Up", "Follow Up", "Call Later", "Callback"]:
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

    if status_filter and status_filter.lower() != "all":
        # Handle mapped statuses matching pipeline_stats logic (Case Insensitive)
        if status_filter == "Attempted":
             query = query.filter(func.lower(Lead.status).in_([
                 "attempted", "ringing", "busy", "not reachable", 
                 "switch off", "no answer",
                 "connected", "contacted", "in conversation"
             ]))
        elif status_filter == "Converted":
             query = query.filter(func.lower(Lead.status) == "converted")
        elif status_filter == "Connected":
             query = query.filter(func.lower(Lead.status).in_([
                 "connected", "contacted", "in conversation"
             ]))
        elif status_filter == "Interested":
             query = query.filter(func.lower(Lead.status).in_([
                 "interested", "meeting scheduled", "demo scheduled"
             ]))
        elif status_filter == "Follow-Up":
             query = query.filter(func.lower(Lead.status).in_([
                 "follow-up", "follow up", "call later", "callback"
             ]))
        elif status_filter == "Won":
             query = query.filter(func.lower(Lead.status).in_(["won", "closed"]))
        elif status_filter == "Lost":
             query = query.filter(func.lower(Lead.status).in_([
                 "lost", "junk", "wrong number", "invalid", "not interested", "not intersted"
             ]))
        elif status_filter == "New":
             query = query.filter(func.lower(Lead.status) == "new")
        else:
             # Fallback for direct match (e.g. specific status like "Ringing" if selected directly)
             query = query.filter(func.lower(Lead.status) == status_filter.lower())

    # Source Filter
    source_filter = request.args.get("source")
    if source_filter and source_filter.lower() != "all":
        query = query.filter(func.lower(Lead.source) == source_filter.lower())

    # Search Filter (Name or Phone)
    search = request.args.get("search")
    if search:
        search_term = f"%{search}%"
        query = query.filter(or_(
            Lead.name.ilike(search_term),
            Lead.phone.ilike(search_term)
        ))

    # Date Filter
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    timezone_offset = request.args.get("timezone_offset", type=int) # JS offset (UTC - Local) in minutes

    if start_date:
        try:
            # Parse Local Start Date
            s_dt = datetime.strptime(start_date, "%Y-%m-%d") # 00:00:00 Local
            
            if timezone_offset is not None:
                # Convert Local 00:00 to UTC
                # UTC = Local + Offset
                s_dt = s_dt + timedelta(minutes=timezone_offset)
            
            query = query.filter(Lead.created_at >= s_dt)
        except ValueError:
            pass

    if end_date:
        try:
             # Parse Local End Date (End of Day)
            e_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59) # 23:59:59 Local

            if timezone_offset is not None:
                # Convert Local 23:59 to UTC
                e_dt = e_dt + timedelta(minutes=timezone_offset)

            query = query.filter(Lead.created_at <= e_dt)
        except ValueError:
            pass

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
            "created_at": (lead.created_at.isoformat() + "Z") if lead.created_at else None,
            "assigned_agent_id": lead.assigned_to,
            "assigned_agent_name": agent_name,
            "email": lead.email,
            "property_type": lead.property_type,
            "location": lead.location,
            "budget": lead.budget,
            "requirement": lead.requirement,
            "custom_fields": lead.custom_fields
        })

    return jsonify({
        "leads": data,
        "current_page": page,
        "pages": paginated.pages,
        "total_leads": paginated.total
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
    # Fix: Case insensitive check
    won_counts = db.session.query(Lead.assigned_to, func.count(Lead.id)).filter(
        Lead.admin_id == admin_id,
        func.lower(Lead.status).in_(["converted", "won", "closed"]),
        Lead.updated_at >= month_start,
        Lead.updated_at < month_end
    ).group_by(Lead.assigned_to).all()
    won_map = {uid: count for uid, count in won_counts}

    data = []
    for u in users:
        data.append({
            "id": u.id,
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


@pipeline_bp.route("/kanban", methods=["GET"])
@jwt_required()
def kanban_leads():
    """
    Fetch all leads for the Odoo-style Kanban board.
    """
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    
    # Fetch recent leads
    leads = Lead.query.filter_by(admin_id=admin_id).order_by(Lead.created_at.desc()).limit(500).all()
    
    # Bulk Fetch Call Stats (Count & Max Duration) for these leads
    # Optimization: Filter by phones in the leads list to avoid full table scan
    lead_phones = [l.phone for l in leads if l.phone] 
    
    call_stats = {}
    if lead_phones:
        # Group by phone, get count and max duration
        stats_query = db.session.query(
            CallHistory.phone_number, 
            func.count(CallHistory.id), 
            func.max(CallHistory.duration)
        ).filter(
            CallHistory.phone_number.in_(lead_phones)
        ).group_by(CallHistory.phone_number).all()
        
        for phone, count, max_dur in stats_query:
            call_stats[phone] = {"count": count, "max_dur": (max_dur or 0)}

    # Initialize 6 standard stages per Odoo Design
    columns = {
        "New": [],
        "Attempted": [],
        "Connected": [],
        "Converted": [],
        "Won": [],
        "Lost": []
    }

    for lead in leads:
        try:
            # Resolve Assigned Agent Name
            agent_name = (lead.assignee.name if lead.assignee and lead.assignee.name else "Unassigned")
            
            # Parse Revenue from Budget (e.g. "50000" or "50k")
            revenue = 0
            try:
                if lead.budget:
                    # Remove common non-numeric chars
                    clean_budget = "".join(filter(str.isdigit, str(lead.budget)))
                    if clean_budget:
                        revenue = int(clean_budget)
            except:
                revenue = 0

            # Determine Tags
            tags = []
            if lead.property_type:
                tags.append({"text": lead.property_type, "color": "purple"})
            if lead.source:
                 tags.append({"text": lead.source, "color": "blue"})

            # --- RATING LOGIC ---
            # 1. Check Manual Override first
            manual_rating = 0
            if lead.custom_fields and isinstance(lead.custom_fields, dict):
                 manual_rating = int(lead.custom_fields.get('priority', 0))

            if manual_rating > 0:
                rating = manual_rating
            else:
                # 2. Automatic Logic (1-5 Stars)
                rating = 3 # Default
                
                stats = call_stats.get(lead.phone, {"count": 0, "max_dur": 0})
                call_count = stats["count"]
                max_duration = stats["max_dur"] or 0 # Handle NoneType for max_dur
                
                s_lower = (lead.status or "").lower()

                # Rule 1: Green (5 Stars)
                if max_duration > 180 or revenue > 50000 or s_lower in ['won', 'converted', 'closed']:
                    rating = 5
                # Rule 2: Red (1 Star)
                elif (call_count >= 3 and max_duration == 0) or s_lower in ['lost', 'junk', 'invalid', 'not interested']:
                    rating = 1
                # Rule 3: Yellow (3 Stars)
                else:
                    rating = 3

            item = {
                "id": lead.id,
                "name": lead.name or "Unknown",
                "phone": lead.phone,
                "email": lead.email,
                "source": lead.source, 
                "revenue": revenue,
                "budget_display": lead.budget or "",
                "property_type": lead.property_type,
                "location": lead.location,
                "requirement": lead.requirement,
                "tags": tags,
                "agent": agent_name,
                "agent_avatar": (agent_name[:2].upper() if agent_name else "NA"),
                "priority": rating,
                "call_stats": f"{call_count} calls, max {max_duration}s" if 'call_count' in locals() else "", 
                "status": lead.status,
                "created_at": (lead.created_at.isoformat() + "Z") if lead.created_at else None
            }

            # Normalize Status to Column
            s_norm = (lead.status or "New").capitalize()

            # Direct Matches
            if s_norm in columns:
                columns[s_norm].append(item)
                continue
                
            # Mapped Matches
            s_lower = s_norm.lower()
            
            if s_lower in ["new", "new leads", "new lead"]:
                 columns["New"].append(item)
            elif s_lower in ["attempted", "ringing", "busy", "not reachable", "switch off", "no answer"]:
                 columns["Attempted"].append(item)
            elif s_lower in ["connected", "contacted", "in conversation", "follow-up", "follow up", "call later", "callback", "meeting scheduled"]:
                 columns["Connected"].append(item)
            elif s_lower in ["converted", "interested", "proposition", "qualified", "demo scheduled"]:
                 columns["Converted"].append(item)
            elif s_lower in ["won", "closed"]:
                 columns["Won"].append(item)
            elif s_lower in ["lost", "junk", "wrong number", "invalid", "not interested"]:
                 columns["Lost"].append(item)
            else:
                 # Default fallback
                 columns["New"].append(item)
        except Exception as e:
            print(f"Skipping bad lead {lead.id}: {str(e)}")
            continue

    return jsonify({"kanban": columns}), 200


@pipeline_bp.route("/update_status/<int:lead_id>", methods=["POST"])
@jwt_required()
def update_lead_status(lead_id):
    """
    Update lead status (drag & drop).
    """
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    
    data = request.get_json()
    new_status = data.get("status")

    if not new_status:
        return jsonify({"error": "Status is required"}), 400

    lead = Lead.query.filter_by(id=lead_id, admin_id=admin_id).first()
    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    # Update
    lead.status = new_status
    lead.updated_at = datetime.utcnow()
    
    db.session.commit()

    return jsonify({"message": "Status updated successfully"}), 200


@pipeline_bp.route("/leads", methods=["POST"])
@jwt_required()
def create_lead():
    """Create a new lead manually."""
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    data = request.get_json()

    if not data.get("name") or not data.get("phone"):
        return jsonify({"error": "Name and Phone are required"}), 400

    try:
        custom_fields = {}
        if "priority" in data:
             custom_fields['priority'] = int(data["priority"])

        lead = Lead(
            admin_id=admin_id,
            name=data.get("name"),
            phone=data.get("phone"),
            email=data.get("email"),
            source=data.get("source", "manual"),
            status=data.get("status", "new"),
            budget=data.get("budget"),
            property_type=data.get("property_type"),
            location=data.get("location"),
            requirement=data.get("requirement"),
            assigned_to=int(data.get("assigned_to")) if data.get("assigned_to") else None,
            custom_fields=custom_fields
        )
        db.session.add(lead)
        db.session.commit()
        return jsonify({"message": "Lead created", "lead": lead.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@pipeline_bp.route("/leads/<int:lead_id>", methods=["PUT"])
@jwt_required()
def update_lead_details(lead_id):
    """Update lead details."""
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    lead = Lead.query.filter_by(id=lead_id, admin_id=admin_id).first()
    
    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    data = request.get_json()
    try:
        if "name" in data: lead.name = data["name"]
        if "phone" in data: lead.phone = data["phone"]
        if "email" in data: lead.email = data["email"]
        if "budget" in data: lead.budget = data["budget"]
        if "status" in data: lead.status = data["status"]
        if "source" in data: lead.source = data["source"]
        if "property_type" in data: lead.property_type = data["property_type"]
        if "location" in data: lead.location = data["location"]
        if "requirement" in data: lead.requirement = data["requirement"]
        if "assigned_to" in data: 
            val = data["assigned_to"]
            lead.assigned_to = int(val) if val else None

        # Update Priority in custom_fields
        if "priority" in data:
            cf = dict(lead.custom_fields) if lead.custom_fields else {}
            cf['priority'] = int(data["priority"])
            lead.custom_fields = cf # Reassign to trigger update
            # Force mutable tracking if needed, but reassignment works

        lead.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "Lead updated", "lead": lead.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@pipeline_bp.route("/leads/<int:lead_id>", methods=["DELETE"])
@jwt_required()
def delete_lead(lead_id):
    """Delete a lead."""
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    lead = Lead.query.filter_by(id=lead_id, admin_id=admin_id).first()
    
    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    try:
        db.session.delete(lead)
        db.session.commit()
        return jsonify({"message": "Lead deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
