from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Lead, User, now
from datetime import datetime

bp = Blueprint("agent_leads", __name__, url_prefix="/api/agent")

# =========================================================
# 1. GET MY LEADS (Assigned to logged-in agent)
# =========================================================
@bp.route("/leads", methods=["GET"])
@jwt_required()
def get_my_leads():
    try:
        user_id = int(get_jwt_identity())
        
        # Verify user exists and is active
        user = User.query.get(user_id)
        if not user or not user.is_active:
            return jsonify({"error": "User not found or inactive"}), 403

        # Filters
        status = request.args.get("status")
        search = request.args.get("search")
        
        query = Lead.query.filter_by(assigned_to=user_id)
        
        if status and status.lower() != "all":
            # Normalize status check
            s_lower = status.lower()
            if s_lower == "new":
                query = query.filter(Lead.status == "new")
            elif s_lower == "attempted":
                 query = query.filter(Lead.status.in_([
                     "Attempted", "Ringing", "Busy", "Not Reachable", 
                     "Switch Off", "No Answer"
                 ]))
            elif s_lower == "connected":
                 query = query.filter(Lead.status.in_([
                     "Connected", "Contacted", "In Conversation"
                 ]))
            elif s_lower == "interested":
                 query = query.filter(Lead.status.in_([
                     "Interested", "Meeting Scheduled", "Demo Scheduled"
                 ]))
            elif s_lower == "follow-up":
                 query = query.filter(Lead.status.in_([
                     "Follow-Up", "Call Later", "Callback"
                 ]))
            elif s_lower == "converted":
                 query = query.filter(Lead.status.in_(["Converted", "Won", "Closed"]))
            elif s_lower == "lost":
                 query = query.filter(Lead.status.in_([
                     "Lost", "Junk", "Wrong Number", "Invalid", "Not Interested"
                 ]))
            else:
                 query = query.filter(Lead.status == status)

        if search:
            query = query.filter(Lead.name.ilike(f"%{search}%") | Lead.phone.ilike(f"%{search}%"))

        # Sort by latest
        leads = query.order_by(Lead.created_at.desc()).limit(100).all()
        
        return jsonify({
            "leads": [l.to_dict() for l in leads]
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================================
# 2. UPDATE LEAD STATUS
# =========================================================
@bp.route("/leads/<int:lead_id>/status", methods=["PUT"])
@jwt_required()
def update_lead_status(lead_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        new_status = data.get("status")
        
        if not new_status:
            return jsonify({"error": "Status is required"}), 400

        # Ensure lead belongs to this agent
        lead = Lead.query.filter_by(id=lead_id, assigned_to=user_id).first()
        if not lead:
            return jsonify({"error": "Lead not found or reference mismatch"}), 404

        # Update
        lead.status = new_status
        lead.updated_at = now()
        db.session.commit()
        
        return jsonify({
            "message": "Status updated",
            "lead_id": lead.id,
            "new_status": new_status
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# =========================================================
# 3. REGISTER FCM TOKEN (For Push Notifications)
# =========================================================
@bp.route("/fcm-token", methods=["POST"])
@jwt_required()
def update_fcm_token():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        token = data.get("fcm_token")
        
        if not token:
            return jsonify({"error": "Token is required"}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        user.fcm_token = token
        db.session.commit()
        
        return jsonify({"message": "FCM Token registered"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
