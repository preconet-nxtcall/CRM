from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import db, Lead, Campaign, User
from sqlalchemy import func, case

admin_lead_analytics_bp = Blueprint("admin_lead_analytics", __name__, url_prefix="/api/admin/analytics")

def admin_required():
    claims = get_jwt()
    return claims.get("role") == "admin"

@admin_lead_analytics_bp.route("/leads", methods=["GET"])
@jwt_required()
def lead_analytics():
    """
    Get detailed lead analytics:
    1. Leads by Source
    2. Leads by Status (Conversion Pipeline)
    3. Campaign Performance
    """
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    
    # 1. Leads by Source
    source_stats = db.session.query(
        Lead.source, func.count(Lead.id)
    ).filter(Lead.admin_id == admin_id).group_by(Lead.source).all()
    
    source_data = {s or "Unknown": c for s, c in source_stats}

    # 2. Leads by Status (Funnel)
    status_stats = db.session.query(
        Lead.status, func.count(Lead.id)
    ).filter(Lead.admin_id == admin_id).group_by(Lead.status).all()
    
    status_data = {s or "New": c for s, c in status_stats}
    
    # Calculate Conversion Rate (Closed / Total)
    total_leads = sum(status_data.values())
    closed_leads = status_data.get("closed", 0) + status_data.get("won", 0)
    conversion_rate = round((closed_leads / total_leads * 100), 2) if total_leads > 0 else 0

    # 3. Campaign Performance
    campaign_stats = db.session.query(
        Campaign.name, func.count(Lead.id)
    ).join(Lead, Lead.campaign_id == Campaign.id)\
     .filter(Campaign.admin_id == admin_id)\
     .group_by(Campaign.name).all()
     
    campaign_data = {c: count for c, count in campaign_stats}

    # 4. Agent Performance (Leads Assigned vs Converted)
    # This is a bit complex, we want: Agent Name -> {assigned: X, converted: Y}
    agent_stats = db.session.query(
        User.name, 
        func.count(Lead.id),
        func.sum(case((Lead.status == 'Closed', 1), else_=0))
    ).join(Lead, Lead.assigned_to == User.id)\
     .filter(Lead.admin_id == admin_id)\
     .group_by(User.name).all()
     
    agent_data = []
    for name, total, converted in agent_stats:
        agent_data.append({
            "name": name,
            "assigned": total,
            "converted": converted or 0,
            "conversion_rate": round(((converted or 0) / total * 100), 1) if total > 0 else 0
        })

    # 5. Average Response Time (Approx: Assignment Time -> First Update)
    # Using specific status change would be better but requires ActivityLog parsing.
    # We will use (Lead.updated_at - Lead.assignment_time) for leads that are NO LONGER 'New'.
    # This assumes 'updated_at' captures the first interaction reasonably well for MVP.
    
    # Postgres/SQLAlchemy interval extraction can vary.
    # We will fetch raw seconds avg.
    # Note: timestamp subtraction returns Interval.
    
    avg_response_query = db.session.query(
        func.avg(Lead.updated_at - Lead.assignment_time)
    ).filter(
        Lead.admin_id == admin_id,
        Lead.status != 'New',
        Lead.assignment_time.isnot(None),
        Lead.updated_at > Lead.assignment_time
    ).scalar()
    
    # Convert timedelta/interval to minutes
    avg_response_minutes = 0
    if avg_response_query:
        # If it returns a timedelta object (Flask-SQLAlchemy often does)
        try:
            avg_response_minutes = round(avg_response_query.total_seconds() / 60, 1)
        except:
            # If it returns generic number (depending on DB driver)
            avg_response_minutes = avg_response_query

    return jsonify({
        "total_leads": total_leads,
        "conversion_rate": conversion_rate,
        "avg_response_time_min": avg_response_minutes,
        "by_source": source_data,
        "by_status": status_data,
        "by_campaign": campaign_data,
        "agent_performance": agent_data
    })
