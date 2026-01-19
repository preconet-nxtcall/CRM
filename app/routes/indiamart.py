from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import db, IndiamartSettings, Admin, User, now


bp = Blueprint('indiamart', __name__)

# =======================================================
#  CONFIGURATION
# =======================================================

@bp.route('/api/indiamart/status', methods=['GET'])
@jwt_required()
def get_status():
    """
    Check if IndiaMART is connected for the current Admin.
    """
    try:
        claims = get_jwt()
        role = claims.get('role')
        current_id = int(get_jwt_identity())

        if role == 'admin':
            admin = Admin.query.get(current_id)
        elif role == 'user':
            # Option: Allow agents to see status? 
            # For now, if code expects strict admin settings management:
            return jsonify({"error": "Admin privileges required"}), 403
        else:
            return jsonify({"error": "Unauthorized"}), 403

        if not admin:
            return jsonify({"error": "Admin account not found"}), 404

        settings = IndiamartSettings.query.filter_by(admin_id=admin.id).first()
        
        if settings:
            return jsonify({
                "connected": True,
                "settings": settings.to_dict()
            }), 200
        
        return jsonify({"connected": False}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/indiamart/connect', methods=['POST'])
@jwt_required()
def connect():
    """
    Save IndiaMART Mobile and API Key.
    Expects: { mobile_number, api_key }
    """
    try:
        claims = get_jwt()
        role = claims.get('role')
        current_id = int(get_jwt_identity())

        if role != 'admin':
             return jsonify({"error": "Only Admins can connect integrations"}), 403

        admin = Admin.query.get(current_id)
        if not admin:
             return jsonify({"error": "Admin account not found"}), 404

        data = request.json
        mobile = data.get('mobile_number')
        api_key = data.get('api_key')

        if not mobile or not api_key:
            return jsonify({"error": "Mobile Number and API Key are required"}), 400

        # Update or Create
        settings = IndiamartSettings.query.filter_by(admin_id=admin.id).first()
        
        if not settings:
            settings = IndiamartSettings(admin_id=admin.id)
        
        settings.mobile_number = mobile
        settings.set_api_key(api_key)  # Encrypts automatically
        
        # Update auto_sync if provided
        if 'auto_sync' in data:
             settings.auto_sync_enabled = bool(data['auto_sync'])
             
        settings.updated_at = now()

        db.session.add(settings)
        db.session.commit()

        return jsonify({"message": "IndiaMART connected successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route('/api/indiamart/disconnect', methods=['POST'])
@jwt_required()
def disconnect():
    try:
        claims = get_jwt()
        role = claims.get('role')
        current_id = int(get_jwt_identity())

        if role != 'admin':
             return jsonify({"error": "Only Admins can disconnect integrations"}), 403
             
        admin = Admin.query.get(current_id)
        if not admin:
             return jsonify({"error": "Admin account not found"}), 404
        
        settings = IndiamartSettings.query.filter_by(admin_id=admin.id).first()
        if settings:
            db.session.delete(settings)
            db.session.commit()
        
        return jsonify({"message": "Disconnected"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# =======================================================
#  SYNC LEADS
# =======================================================

@bp.route('/api/indiamart/sync', methods=['POST'])
@jwt_required()
def sync_leads():
    """
    Fetch leads from IndiaMART API and save to DB.
    """
    try:
        claims = get_jwt()
        role = claims.get('role')
        current_id = int(get_jwt_identity())

        if role == 'admin':
            admin = Admin.query.get(current_id)
        else:
            return jsonify({"error": "Admin privileges required"}), 403
            
        if not admin:
             return jsonify({"error": "Admin account not found"}), 404

        from app.services.indiamart_service import sync_admin_leads
        
        result = sync_admin_leads(admin.id)
        
        if result.get("status") == "error":
             code = 500
             if "IndiaMART API Error" in result.get("error", ""): code = 502
             if "not connected" in result.get("error", ""): code = 400
             return jsonify(result), code
        
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
