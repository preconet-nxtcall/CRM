from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.models import db, Campaign, User, Admin
from app.services.campaign_service import CampaignService

bp = Blueprint('campaigns', __name__, url_prefix='/api/campaigns')

@bp.route('/', methods=['GET'])
@jwt_required()
def get_campaigns():
    try:
        current_identity = int(get_jwt_identity())
        # Assume Admin for now
        campaigns = CampaignService.get_campaigns(current_identity)
        return jsonify([c.to_dict() for c in campaigns]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/create', methods=['POST'])
@jwt_required()
def create_campaign():
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description')
        
        if not name:
            return jsonify({"error": "Name required"}), 400
            
        current_identity = int(get_jwt_identity())
        
        campaign = CampaignService.create_campaign(current_identity, name, description)
        
        if campaign:
            return jsonify(campaign.to_dict()), 201
        else:
            return jsonify({"error": "Failed to create campaign"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/<int:campaign_id>/agents', methods=['POST'])
@jwt_required()
def update_agents(campaign_id):
    """
    Update agents assigned to a campaign.
    Body: { "agent_ids": [1, 2, 3] }
    """
    try:
        data = request.json
        agent_ids = data.get('agent_ids', [])
        
        success = CampaignService.update_campaign_agents(campaign_id, agent_ids)
        
        if success:
            return jsonify({"message": "Agents updated"}), 200
        else:
            return jsonify({"error": "Failed to update agents"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
