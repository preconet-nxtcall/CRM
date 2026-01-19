
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import db, MagicbricksSettings, Admin, now
from app.services.magicbricks_service import sync_magicbricks_leads, get_imap_connection

bp = Blueprint('magicbricks', __name__)

@bp.route('/api/magicbricks/status', methods=['GET'])
@jwt_required()
def get_mb_status():
    """
    Get Connection Status and Last Sync Time
    """
    current_id = int(get_jwt_identity())
    
    settings = MagicbricksSettings.query.filter_by(admin_id=current_id).first()
    
    if not settings:
        return jsonify({"connected": False}), 200
        
    return jsonify({
        "connected": bool(settings.app_password),
        "settings": settings.to_dict()
    }), 200

@bp.route('/api/magicbricks/connect', methods=['POST'])
@jwt_required()
def connect_mb():
    """
    Connect to Magicbricks via IMAP
    """
    data = request.json
    current_id = int(get_jwt_identity())
    
    email_id = data.get('email')
    app_password = data.get('app_password')
    imap_host = data.get('imap_host', 'imap.gmail.com')
    
    if not email_id or not app_password:
        return jsonify({"error": "Email and App Password required"}), 400
        
    try:
        # Check if settings exist, else create
        settings = MagicbricksSettings.query.filter_by(admin_id=current_id).first()
        if not settings:
            settings = MagicbricksSettings(admin_id=current_id)
            
        settings.email_id = email_id
        settings.imap_host = imap_host
        settings.set_app_password(app_password)
        settings.is_active = True
        
        # Test Connection Immediate
        get_imap_connection(settings).logout() # Will throw if fails
        
        db.session.add(settings)
        db.session.commit()
        
        return jsonify({"message": "Connected successfully"}), 200
        
    except Exception as e:
        return jsonify({"error": f"Connection failed: {str(e)}"}), 400

@bp.route('/api/magicbricks/sync', methods=['POST'])
@jwt_required()
def sync_mb():
    """
    Trigger Manual Sync
    """
    current_id = int(get_jwt_identity())
    
    try:
        result = sync_magicbricks_leads(current_id)
        if result.get("status") == "error":
             return jsonify({"error": result.get("message")}), 400
             
        return jsonify({
            "message": "Sync complete",
            "added": result.get("added", 0)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/api/magicbricks/disconnect', methods=['POST'])
@jwt_required()
def disconnect_mb():
    """
    Remove Settings
    """
    current_id = int(get_jwt_identity())
    
    try:
        settings = MagicbricksSettings.query.filter_by(admin_id=current_id).first()
        if settings:
             db.session.delete(settings)
             db.session.commit()
             
        return jsonify({"message": "Disconnected"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
