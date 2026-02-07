
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import db, NinetyNineAcresSettings, Admin, now
from app.services.ninety_nine_acres_service import sync_99acres_leads, get_imap_connection

bp = Blueprint('ninety_nine_acres', __name__)

@bp.route('/api/99acres/status', methods=['GET'])
@jwt_required()
def get_99acres_status():
    """
    Get Connection Status and Last Sync Time
    """
    current_id = int(get_jwt_identity())
    
    settings = NinetyNineAcresSettings.query.filter_by(admin_id=current_id).first()
    
    if not settings:
        return jsonify({"connected": False}), 200
        
    return jsonify({
        "connected": bool(settings.app_password),
        "settings": settings.to_dict()
    }), 200

@bp.route('/api/99acres/connect', methods=['POST'])
@jwt_required()
def connect_99acres():
    """
    Connect to 99acres via IMAP
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
        settings = NinetyNineAcresSettings.query.filter_by(admin_id=current_id).first()
        if not settings:
            settings = NinetyNineAcresSettings(admin_id=current_id)
            
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

import threading

@bp.route('/api/99acres/sync', methods=['POST'])
@jwt_required()
def sync_99acres():
    """
    Trigger Manual Sync (Async)
    """
    current_id = int(get_jwt_identity())
    
    try:
        # Spawn Background Thread
        thread = threading.Thread(target=run_99acres_sync_async, args=(current_app._get_current_object(), current_id))
        thread.start()

        return jsonify({"message": "Sync started in background"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_99acres_sync_async(app, admin_id):
    with app.app_context():
        try:
            app.logger.info(f"Starting 99acres Sync for {admin_id}")
            result = sync_99acres_leads(admin_id)
            app.logger.info(f"99acres Sync Result: {result}")
        except Exception as e:
            app.logger.error(f"99acres Sync Failed: {e}")

@bp.route('/api/99acres/disconnect', methods=['POST'])
@jwt_required()
def disconnect_mb():
    """
    Remove Settings
    """
    current_id = int(get_jwt_identity())
    
    try:
        settings = NinetyNineAcresSettings.query.filter_by(admin_id=current_id).first()
        if settings:
             db.session.delete(settings)
             db.session.commit()
             
        return jsonify({"message": "Disconnected"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
