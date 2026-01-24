from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import Admin, Lead, db, now
from app.services.lead_service import LeadService

bp = Blueprint('leads', __name__)

@bp.route('/api/leads/ingest', methods=['POST'])
@jwt_required(optional=True) 
def ingest_lead_api():
    """
    Generic endpoint to ingest leads from Website/landing pages.
    Now accepts optional 'campaign_id'.
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Authentication logic
        identity = get_jwt_identity()
        admin_id = None
        
        if identity:
            # Assume Admin ID if logged in (Simplification)
            admin_id = int(identity) 
        
        # Allow passing admin_id explicitly (e.g. public webhook with ID)
        if not admin_id and 'admin_id' in data:
            admin_id = data.get('admin_id')

        if not admin_id:
             return jsonify({"error": "Admin ID required"}), 401

        source = data.get('source', 'website')
        campaign_id = data.get('campaign_id')
        
        lead = LeadService.ingest_lead(admin_id, source, data, campaign_id)
        
        if lead:
            return jsonify({"message": "Lead ingested successfully", "lead_id": lead.id}), 201
        else:
             return jsonify({"error": "Ingestion failed"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/api/leads/<int:lead_id>/status', methods=['PUT'])
@jwt_required()
def update_lead_status(lead_id):
    """
    Update Lead Status and optionally schedule a follow-up.
    """
    try:
        data = request.json
        status = data.get('status')
        
        if not status:
            return jsonify({"error": "Status required"}), 400
            
        # Auth Check
        claims = get_jwt()
        role = claims.get("role")
        identity = int(get_jwt_identity())
        
        lead = Lead.query.get_or_404(lead_id)
        
        # Permission Check
        if role == "user":
            if lead.assigned_to != identity:
                return jsonify({"error": "Unauthorized"}), 403
        elif role == "admin":
            if lead.admin_id != identity:
                return jsonify({"error": "Unauthorized"}), 403
                
        # Validate Status Transition (Neodove Pipeline + Legacy Support)
        valid_statuses = [
            "New", 
            "Attempted", "Connected", "Contacted",  # Pipeline Stages
            "Interested", "Follow-Up", "Follow Up", # Handle both formats
            "Not Interested", "Closed", "Lost",     # Closed/Negative
            "Won"                                   # Sales
        ]
        if status not in valid_statuses:
             return jsonify({"error": f"Invalid status. Must be one of {valid_statuses}"}), 400

        # Create Activity Log
        from app.models import ActivityLog, UserRole
        
        log = ActivityLog(
            actor_role=UserRole.USER if role == "user" else UserRole.ADMIN,
            actor_id=identity,
            action=f"Changed status from {lead.status} to {status}",
            target_type="LEAD",
            target_id=lead.id,
            timestamp=now()    
        )
        db.session.add(log)

        # Update Status
        old_status = lead.status
        lead.status = status
        lead.updated_at = now()
        
        # Handle Follow-up Automation
        if status == "Follow-up" and data.get("followup_date"):
            from app.models import Followup
            from datetime import datetime
            import uuid
            reminder_id = uuid.uuid4().hex
            
            date_time_str = data.get("followup_date")
            try:
                date_time = datetime.fromisoformat(date_time_str.replace('Z', '+00:00'))
                if date_time.tzinfo: date_time = date_time.replace(tzinfo=None)
                
                msg = data.get("followup_message", "Scheduled Follow-up")
                
                fup = Followup(
                    id=reminder_id,
                    user_id=lead.assigned_to,
                    contact_name=lead.name,
                    phone=lead.phone,
                    message=msg,
                    date_time=date_time,
                    status="pending"
                )
                db.session.add(fup)
            except Exception as e:
                 return jsonify({"error": f"Invalid date format: {e}"}), 400

        db.session.commit()
        
        return jsonify({
            "message": "Status updated", 
            "lead_id": lead.id, 
            "old_status": old_status, 
            "new_status": status
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
