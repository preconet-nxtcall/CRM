
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, HousingSettings, now
from app.services.housing_service import sync_housing_leads, get_imap_connection

bp = Blueprint('housing', __name__)

@bp.route('/api/housing/connect', methods=['POST'])
@jwt_required()
def connect_housing():
    try:
        current_user_id = int(get_jwt_identity())
        data = request.json
        

        email_id = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        if not email_id or not password:
            return jsonify({"error": "Email and App Password are required"}), 400

        # Create/Update Settings
        settings = HousingSettings.query.filter_by(admin_id=current_user_id).first()
        if not settings:
            settings = HousingSettings(admin_id=current_user_id)
            
        settings.email_id = email_id
        settings.set_app_password(password)
        settings.imap_host = "imap.gmail.com" # Default
        settings.is_active = True
        
        # Test Connection
        try:
            mail = get_imap_connection(settings)
            mail.logout()


        except Exception as e:
             error_msg = str(e)
             # Cleanup bytes representation from imaplib errors
             if "b'" in error_msg or 'b"' in error_msg:
                 try:
                     # Extract content inside b'...'
                     import re
                     match = re.search(r"b['\"](.*?)['\"]", error_msg)
                     if match:
                         error_msg = match.group(1)
                         # Try to fix escaped chars if any
                         error_msg = error_msg.replace('\\r\\n', ' ').strip()
                 except:
                     pass
             return jsonify({"error": f"Connection Failed: {error_msg}"}), 400

        db.session.add(settings)
        db.session.commit()
        
        return jsonify({"message": "Connected successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/api/housing/status', methods=['GET'])
@jwt_required()
def get_housing_status():
    try:
        current_user_id = int(get_jwt_identity())
        settings = HousingSettings.query.filter_by(admin_id=current_user_id).first()
        
        if settings and settings.is_active:
            return jsonify(settings.to_dict()), 200
        
        return jsonify({"is_connected": False}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/api/housing/sync', methods=['POST'])
@jwt_required()
def sync_housing():
    try:
        current_user_id = int(get_jwt_identity())
        result = sync_housing_leads(current_user_id)
        if result['status'] == 'error':
            return jsonify(result), 400
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/api/housing/disconnect', methods=['POST'])
@jwt_required()
def disconnect_housing():
    try:
        current_user_id = int(get_jwt_identity())
        settings = HousingSettings.query.filter_by(admin_id=current_user_id).first()
        
        if settings:
            db.session.delete(settings)
            db.session.commit()
            
        return jsonify({"message": "Disconnected"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
