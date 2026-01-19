from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import db, IndiamartSettings, Lead, Admin, User, now
import requests
import datetime

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
    try:
        claims = get_jwt()
        role = claims.get('role')
        current_id = int(get_jwt_identity())

        if role == 'admin':
            admin = Admin.query.get(current_id)
        else:
            # Agents typically shouldn't trigger manual sync, but if needed:
            # user = User.query.get(current_id); admin = Admin.query.get(user.admin_id)
            return jsonify({"error": "Admin privileges required"}), 403
            
        if not admin:
             return jsonify({"error": "Admin account not found"}), 404

        settings = IndiamartSettings.query.filter_by(admin_id=admin.id).first()
        if not settings:
            return jsonify({"error": "IndiaMART is not connected. Please connect first."}), 400

        # Prepare API Request
        api_url = "https://api.indiamart.com/wservce/crm/crmListing/v2/"
        
        # Decrypt API Key
        glusr_mobile_key = settings.get_api_key()
        
        if not glusr_mobile_key:
             return jsonify({'error': 'Invalid API configuration (Encryption Error)'}), 500
        
        params = {
            "glusr_mobile": settings.mobile_number,
            "glusr_mobile_key": glusr_mobile_key,
        }
        
        # Incremental Sync: Use last_sync_time if available
        # IndiaMART format: d-M-Y H:i:s => 01-Jan-2023 10:00:00
        if settings.last_sync_time:
            # Add small buffer to avoid missing leads on the boundary
            start_time = settings.last_sync_time - datetime.timedelta(minutes=5)
            # Python strftime %b is Jan, Feb...
            params["start_time"] = start_time.strftime("%d-%b-%Y %H:%M:%S")
            params["end_time"] = now().strftime("%d-%b-%Y %H:%M:%S")

        current_app.logger.info(f"Syncing IndiaMART for Admin {admin.id} with params: {params}")

        # Call IndiaMART
        resp = requests.post(api_url, json=params, timeout=30)
        
        # IndiaMART sometimes returns 200 even with errors in JSON
        if resp.status_code != 200:
            return jsonify({"error": f"IndiaMART API Error: {resp.status_code}", "details": resp.text}), 502

        data = resp.json()
        
        # Check Response Code
        # STATUS: "SUCCESS" or "FAILURE"
        # RESPONSE: [ ... leads ... ]
        
        if data.get("STATUS") != "SUCCESS":
             # Handle "No Data Found" gracefully
             if data.get("CODE") == "404" or "No Data Found" in str(data.get("MESSAGE", "")):
                  # Update sync time anyway so we don't keep polling old range forever
                  settings.last_sync_time = now()
                  db.session.commit()
                  return jsonify({"message": "No new leads found", "count": 0}), 200
             
             return jsonify({"error": f"IndiaMART Error: {data.get('MESSAGE')}"}), 400

        leads_list = data.get("RESPONSE", [])
        added_count = 0
        
        for item in leads_list:
            # Extract Fields
            query_id = item.get("UNIQUE_QUERY_ID")
            sender_name = item.get("SENDER_NAME")
            sender_mobile = item.get("SENDER_MOBILE")
            sender_email = item.get("SENDER_EMAIL")
            subject = item.get("SUBJECT")
            message = item.get("QUERY_MESSAGE")
            sender_company = item.get("SENDER_COMPANY")
            sender_city = item.get("SENDER_CITY")
            sender_state = item.get("SENDER_STATE")
            
            # Check Duplicates (by IndiaMART Query ID in custom_fields)
            # We search custom_fields using JSON path or iterating.
            # Efficient way: Check unique `facebook_lead_id` if we were using it for general ID.
            # But we are using `source` = 'indiamart'.
            
            # Use `facebook_lead_id` column to store UNIQUE_QUERY_ID for fast indexing/uniqueness?
            # Yes, `facebook_lead_id` is unique and indexed. It's a string.
            # Storing IndiaMART ID there is efficient, but might be confusing name-wise.
            # Let's DO IT but prefix it to avoid collision (though unlikely).
            # "IM_" + query_id
            
            im_id = f"IM_{query_id}"
            
            existing = Lead.query.filter_by(facebook_lead_id=im_id, admin_id=admin.id).first()
            if existing:
                continue
                
            # If facebook_lead_id not used, check phone?
            # existing_phone = Lead.query.filter_by(phone=sender_mobile, admin_id=admin.id).first()
            # No, IndiaMART leads might come multiple times for different requirements. ID is better.

            # ---------------------------------------------------------
            # ASSIGNMENT LOGIC (Copy-Paste from Facebook)
            # ---------------------------------------------------------
            assigned_user_id = None
            try:
                active_agents = User.query.filter_by(
                    admin_id=admin.id, 
                    status='active',
                    is_suspended=False
                ).order_by(User.id).all()

                if active_agents:
                    last_lead = Lead.query.filter_by(admin_id=admin.id)\
                        .filter(Lead.assigned_to.isnot(None))\
                        .order_by(Lead.created_at.desc())\
                        .first()

                    if not last_lead or not last_lead.assigned_to:
                        assigned_user_id = active_agents[0].id
                    else:
                        last_agent_id = last_lead.assigned_to
                        agent_ids = [agent.id for agent in active_agents]
                        if last_agent_id in agent_ids:
                            current_index = agent_ids.index(last_agent_id)
                            next_index = (current_index + 1) % len(agent_ids)
                            assigned_user_id = agent_ids[next_index]
                        else:
                            assigned_user_id = agent_ids[0]
            except Exception:
                pass # Assignment failed, leave unassigned

            # Create Lead
            new_lead = Lead(
                admin_id=admin.id,
                facebook_lead_id=im_id, # Storing IM ID here for uniqueness
                name=sender_name,
                email=sender_email,
                phone=sender_mobile,
                source="indiamart",
                status="new",
                assigned_to=assigned_user_id,
                custom_fields={
                    "subject": subject,
                    "message": message,
                    "company": sender_company,
                    "city": sender_city,
                    "state": sender_state,
                    "indiamart_id": query_id
                },
                created_at=now()
            )
            
            db.session.add(new_lead)
            added_count += 1
            
        settings.last_sync_time = now()
        db.session.commit()
        
        return jsonify({
            "message": "Sync complete",
            "added": added_count,
            "total_fetched": len(leads_list)
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"IndiaMART Sync Error: {e}")
        return jsonify({"error": str(e)}), 500
