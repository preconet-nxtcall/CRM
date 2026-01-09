from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, FacebookPage, Lead, Admin
from app.models import now
import requests

facebook_bp = Blueprint('facebook', __name__)

# =======================================================
#  CONNECT FLOW (Admin Context)
# =======================================================

@facebook_bp.route('/api/facebook/status', methods=['GET'])
@jwt_required()
def get_facebook_status():
    """
    Check if the current ADMIN has a connected Facebook Page.
    """
    try:
        current_user_id = int(get_jwt_identity())
        # Verify user is Admin (simple check, assuming JWT from admin login)
        admin = Admin.query.get(current_user_id)
        if not admin:
             return jsonify({"error": "Admin account required"}), 403

        fb_page = FacebookPage.query.filter_by(admin_id=admin.id).first()
        
        if fb_page:
            return jsonify({
                "connected": True,
                "page": {
                    "name": fb_page.page_name,
                    "id": fb_page.page_id
                }
            }), 200
        
        return jsonify({"connected": False}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@facebook_bp.route('/api/facebook/connect', methods=['POST'])
@jwt_required()
def connect_facebook_page():
    """
    Save the Admin's selected Facebook Page and Token.
    Expects: { page_id, page_name, page_access_token }
    """
    try:
        current_user_id = int(get_jwt_identity())
        admin = Admin.query.get(current_user_id)
        if not admin:
            return jsonify({"error": "Admin account required"}), 403

        data = request.json
        page_id = data.get('page_id')
        page_name = data.get('page_name')
        page_access_token = data.get('page_access_token')

        if not all([page_id, page_name, page_access_token]):
            return jsonify({"error": "Missing required fields"}), 400

        # Check if page is already connected to ANOTHER admin
        existing = FacebookPage.query.filter_by(page_id=page_id).first()
        if existing and existing.admin_id != admin.id:
            return jsonify({"error": "This page is already connected to another account."}), 400

        # Update or Create
        fb_page = FacebookPage.query.filter_by(admin_id=admin.id).first()
        
        if not fb_page:
            fb_page = FacebookPage(admin_id=admin.id)
        
        fb_page.page_id = page_id
        fb_page.page_name = page_name
        fb_page.page_access_token = page_access_token
        fb_page.updated_at = now()

        db.session.add(fb_page)
        db.session.commit()

        return jsonify({"message": "Page connected successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@facebook_bp.route('/api/facebook/disconnect', methods=['POST'])
@jwt_required()
def disconnect_facebook_page():
    """
    Remove the connected page.
    """
    try:
        current_user_id = int(get_jwt_identity())
        admin = Admin.query.get(current_user_id)
        if not admin:
             return jsonify({"error": "Admin account required"}), 403
        
        fb_page = FacebookPage.query.filter_by(admin_id=admin.id).first()
        if fb_page:
            db.session.delete(fb_page)
            db.session.commit()
        
        return jsonify({"message": "Disconnected"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# =======================================================
#  WEBHOOK (Server Context)
# =======================================================

@facebook_bp.route('/api/facebook/webhook', methods=['GET'])
def verify_webhook():
    """
    Facebook Verification Handshake
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    verify_token = current_app.config.get('FACEBOOK_VERIFY_TOKEN')

    if mode and token:
        if mode == 'subscribe' and token == verify_token:
            print("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            print(f"WEBHOOK_VERIFICATION_FAILED: Mode={mode}, Token={token}, Expected={verify_token}")
            return 'Verification Failed', 403
    
    return 'Hello Facebook', 200

@facebook_bp.route('/api/facebook/webhook', methods=['POST'])
def handle_webhook():
    """
    Handle incoming lead events.
    """
    data = request.json
    print(f"FB_WEBHOOK_RECEIVED: {data}")

    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            page_id = entry.get('id')
            
            # 1. Find the Admin who owns this page
            fb_page = FacebookPage.query.filter_by(page_id=page_id).first()
            if not fb_page:
                print(f"Warning: Received webhooks for unknown page_id={page_id}")
                continue

            for change in entry.get('changes', []):
                if change.get('field') == 'leadgen':
                    value = change.get('value', {})
                    leadgen_id = value.get('leadgen_id')
                    form_id = value.get('form_id')
                    
                    print(f"Processing Lead: Page={page_id}, LeadGenID={leadgen_id} for Admin={fb_page.admin_id}")
                    
                    try:
                        process_lead(fb_page, leadgen_id, form_id)
                    except Exception as e:
                        print(f"Error processing lead: {e}")

        return 'EVENT_RECEIVED', 200
    
    return 'Not a Page Event', 404


def process_lead(fb_page, leadgen_id, form_id):
    """
    Fetch lead details from Graph API and save to DB.
    """
    # Check if we already have this lead
    existing_lead = Lead.query.filter_by(facebook_lead_id=leadgen_id).first()
    if existing_lead:
        print(f"Lead {leadgen_id} already exists. Skipping.")
        return

    # Fetch from Graph API
    access_token = fb_page.page_access_token
    url = f"https://graph.facebook.com/v18.0/{leadgen_id}?fields=created_time,id,ad_id,form_id,field_data,campaign_name,platform,retailer_item_id&access_token={access_token}"
    
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Failed to fetch lead data: {resp.text}")
        return

    lead_data = resp.json()
    field_data = lead_data.get('field_data', [])
    
    # Parse fields
    parsed_data = {}
    for field in field_data:
        name = field.get('name')
        values = field.get('values', [])
        if values:
            parsed_data[name] = values[0]
            
    # Map common fields
    name = parsed_data.get('full_name') or parsed_data.get('name')
    email = parsed_data.get('email')
    phone = parsed_data.get('phone_number')

    # Save to DB
    new_lead = Lead(
        admin_id=fb_page.admin_id,
        facebook_lead_id=leadgen_id,
        form_id=form_id,
        name=name,
        email=email,
        phone=phone,
        source="facebook",
        status="new",
        custom_fields=parsed_data
    )
    
    db.session.add(new_lead)
    db.session.commit()
    print(f"Lead saved successfully: {name} ({phone})")
