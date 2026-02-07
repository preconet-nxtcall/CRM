
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Admin, JustDialSettings, now
from app.services.justdial_service import sync_justdial_leads, get_imap_connection

bp = Blueprint('justdial', __name__)

@bp.route('/api/justdial/connect', methods=['POST'])
@jwt_required()
def connect_justdial():
    try:
        current_user_id = int(get_jwt_identity())
        data = request.json
        
        email_id = data.get('email')
        password = data.get('password')
        
        if not email_id or not password:
            return jsonify({"error": "Email and App Password are required"}), 400

        # Create/Update Settings
        settings = JustDialSettings.query.filter_by(admin_id=current_user_id).first()
        if not settings:
            settings = JustDialSettings(admin_id=current_user_id)
            
        settings.email_id = email_id
        settings.set_app_password(password)
        settings.imap_host = "imap.gmail.com" # Default
        settings.is_active = True
        
        # Test Connection
        try:
            mail = get_imap_connection(settings)
            mail.logout()
        except Exception as e:
             return jsonify({"error": "Connection Failed. Check credentials."}), 400

        db.session.add(settings)
        db.session.commit()
        
        return jsonify({"message": "Connected successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/api/justdial/status', methods=['GET'])
@jwt_required()
def get_justdial_status():
    try:
        current_user_id = int(get_jwt_identity())
        settings = JustDialSettings.query.filter_by(admin_id=current_user_id).first()
        
        if settings and settings.is_active:
            return jsonify(settings.to_dict()), 200
        
        return jsonify({"is_connected": False}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

import threading

@bp.route('/api/justdial/sync', methods=['POST'])
@jwt_required()
def sync_justdial():
    try:
        current_user_id = int(get_jwt_identity())
        
        # Spawn Background Thread
        thread = threading.Thread(target=run_jd_sync_async, args=(current_app._get_current_object(), current_user_id))
        thread.start()
        
        return jsonify({"message": "Sync started in background"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_jd_sync_async(app, admin_id):
    with app.app_context():
        try:
            app.logger.info(f"Starting JustDial Sync for {admin_id}")
            result = sync_justdial_leads(admin_id)
            app.logger.info(f"JustDial Sync Result: {result}")
        except Exception as e:
            app.logger.error(f"JustDial Sync Failed: {e}")

@bp.route('/api/justdial/disconnect', methods=['POST'])
@jwt_required()
def disconnect_justdial():
    try:
        current_user_id = int(get_jwt_identity())
        settings = JustDialSettings.query.filter_by(admin_id=current_user_id).first()
        
        if settings:
            db.session.delete(settings)
            db.session.commit()
            
        return jsonify({"message": "Disconnected"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
