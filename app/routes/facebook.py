from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import db, FacebookPage, Lead, Admin, User
from app.models import now
import requests
import hmac
import hashlib
import sys

bp = Blueprint('facebook', __name__)

# =======================================================
#  CONNECT FLOW (Admin Context)
# =======================================================

# =======================================================
#  HELPER FUNCTIONS
# =======================================================

def verify_fb_signature(req):
    """
    Verify X-Hub-Signature-256 header.
    """
    signature = req.headers.get("X-Hub-Signature-256")
    app_secret = current_app.config.get("FACEBOOK_APP_SECRET")
    
    if not signature or not app_secret:
        # Log warning if secret not configured, but for security, fail if signature missing
        if not app_secret:
            current_app.logger.warning("WARNING: FACEBOOK_APP_SECRET not set in config.")
        return False

    expected = "sha256=" + hmac.new(
        app_secret.encode(),
        msg=req.data,
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


@bp.route('/api/facebook/status', methods=['GET'])
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


@bp.route('/api/facebook/connect', methods=['POST'])
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

        # Subscribe App to Page Webhooks (subscribed_apps)
        try:
            sub_url = f"https://graph.facebook.com/v24.0/{page_id}/subscribed_apps"
            sub_resp = requests.post(sub_url, params={
                "access_token": page_access_token,
                "subscribed_fields": "leadgen"
            }, timeout=10)
            
            if sub_resp.status_code != 200:
                current_app.logger.error(f"Failed to subscribe app to page: {sub_resp.text}")
                return jsonify({
                    "error": "Failed to subscribe to Page Events. Please check Permissions.",
                    "details": sub_resp.text
                }), 400
                
            current_app.logger.info(f"Successfully subscribed app to page {page_id}")
            
        except Exception as e:
            current_app.logger.error(f"Error subscribing app to page: {e}")
            return jsonify({"error": f"Subscription failed: {str(e)}"}), 500

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



@bp.route('/api/facebook/disconnect', methods=['POST'])
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


@bp.route('/api/facebook/leads', methods=['GET'])
@jwt_required()
def get_leads():
    """
    Get all leads for the current Admin or Agent.
    """
    try:
        claims = get_jwt()
        role = claims.get("role")
        current_identity = int(get_jwt_identity())

        admin_id = None

        if role == "admin":
            admin_id = current_identity
            # Verify admin
            if not Admin.query.get(admin_id):
                 return jsonify({"error": "Admin account required"}), 403
        elif role == "user":
            user = User.query.get(current_identity)
            if not user:
                 return jsonify({"error": "User not found"}), 404
            admin_id = user.admin_id
        else:
             return jsonify({"error": "Unauthorized role"}), 403

        # Pagination & Filtering
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        source_filter = request.args.get('source')

        leads_query = Lead.query.filter_by(admin_id=admin_id)

        if source_filter and source_filter.lower() != 'all':
             leads_query = leads_query.filter(Lead.source == source_filter.lower())

        leads_query = leads_query.order_by(Lead.created_at.desc())
        
        pagination = leads_query.paginate(page=page, per_page=per_page, error_out=False)
        leads = pagination.items

        results = []
        for lead in leads:
            l_dict = lead.to_dict()
            # Add assignee name
            if lead.assignee:
                l_dict['assigned_agent_name'] = lead.assignee.name
            else:
                l_dict['assigned_agent_name'] = "Unassigned"
            
            # Add custom fields (contains campaign info)
            l_dict['custom_fields'] = lead.custom_fields
            
            results.append(l_dict)

        return jsonify({
            "leads": results,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page
        }), 200
    except Exception as e:
        current_app.logger.error(f"Error getting leads: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/facebook/leads/<int:lead_id>/status', methods=['PUT'])
@jwt_required()
def update_lead_status(lead_id):
    """
    Update the status of a specific lead.
    Expects: { "status": "new" | "contacted" | "converted" | "junk" }
    """
    try:
        current_user_id = int(get_jwt_identity())
        admin = Admin.query.get(current_user_id)
        if not admin:
            return jsonify({"error": "Admin account required"}), 403

        lead = Lead.query.filter_by(id=lead_id, admin_id=admin.id).first()
        if not lead:
            return jsonify({"error": "Lead not found"}), 404

        data = request.json
        new_status = data.get("status")
        
        valid_statuses = ["new", "contacted", "qualified", "converted", "junk"]
        if new_status not in valid_statuses:
             return jsonify({"error": f"Invalid status. Allowed: {valid_statuses}"}), 400

        lead.status = new_status
        db.session.commit()

        return jsonify({
            "message": "Status updated successfully",
            "lead": lead.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating lead status: {e}")
        return jsonify({"error": str(e)}), 500


# =======================================================
#  WEBHOOK (Server Context)
# =======================================================



@bp.route('/api/facebook/webhook', methods=['GET', 'POST'])
def handle_webhook():
    """
    Handle incoming lead events.
    VERIFY TOKEN: nxtcall_fb_webhook_2026
    """
    sys.stdout.flush() # FORCE LOG FLUSH
    
    # 1. Verification Request (GET)
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        print(f"DEBUG: Webhook Verification Hit! Mode: {mode}, Token: {token}")
        
        if mode and token:
            if mode == 'subscribe' and token == current_app.config['FACEBOOK_VERIFY_TOKEN']:
                print("DEBUG: Webhook Verified Successfully!")
                return challenge, 200
            else:
                print("DEBUG: Webhook Verification Failed - Token Mismatch")
                return 'Verification token mismatch', 403
        
        return "Webhook is Active and Reachable (GET)", 200

    # 2. Event Notification (POST)
    print("DEBUG: Webhook HIT (POST)! Request received at /api/facebook/webhook") 
    sys.stdout.flush()
    
    if not verify_fb_signature(request):
        current_app.logger.warning("WEBHOOK_SIG_CHECK_FAILED")
        print("DEBUG: Signature Verification Failed")
        return "Invalid signature", 403

    data = request.json
    print(f"DEBUG: Webhook Data: {data}") 
    sys.stdout.flush()
    current_app.logger.info(f"FB_WEBHOOK_RECEIVED: {data}")

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
                    if leadgen_id.startswith("444"):
                        current_app.logger.info(f"Skipping Test Lead {leadgen_id}")
                        continue
                    
                    form_id = value.get('form_id')
                    
                    current_app.logger.info(f"Processing Lead: Page={page_id}, LeadGenID={leadgen_id} for Admin={fb_page.admin_id}")
                    
                    try:
                        process_lead(fb_page, leadgen_id, form_id)
                    except Exception as e:
                        current_app.logger.error(f"Error processing lead: {e}")

        return 'EVENT_RECEIVED', 200
    
    return 'Not a Page Event', 404


def process_lead(fb_page, leadgen_id, form_id):
    """
    Fetch lead details from Graph API and save to DB.
    """
    # Check if we already have this lead
    existing_lead = Lead.query.filter_by(facebook_lead_id=leadgen_id, admin_id=fb_page.admin_id).first()
    if existing_lead:
        current_app.logger.info(f"Lead {leadgen_id} already exists. Skipping.")
        return

    # Fetch from Graph API
    access_token = fb_page.page_access_token
    url = f"https://graph.facebook.com/v24.0/{leadgen_id}?fields=created_time,id,ad_id,ad_name,form_id,field_data,campaign_name,platform,retailer_item_id&access_token={access_token}"
    
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        current_app.logger.error(f"Failed to fetch lead data: {resp.text}")
        return

    lead_data = resp.json()
    field_data = lead_data.get('field_data', [])
    
    if not field_data:
        current_app.logger.warning("Lead data unavailable (likely pending App Review approval or missing permission)")
        return
    
    # Parse fields
    parsed_data = {}
    
    # Store meta info if available
    if lead_data.get('ad_id'):
        parsed_data['ad_id'] = lead_data.get('ad_id')
    if lead_data.get('ad_name'):
        parsed_data['ad_name'] = lead_data.get('ad_name')
    if lead_data.get('campaign_name'):
        parsed_data['campaign_name'] = lead_data.get('campaign_name')
    if lead_data.get('platform'):
        parsed_data['platform'] = lead_data.get('platform')
        
    for field in field_data:
        name = field.get('name')
        values = field.get('values', [])
        if values:
            parsed_data[name] = values[0]
            
    # Map common fields
    name = parsed_data.get('full_name') or parsed_data.get('name')
    email = parsed_data.get('email')
    phone = parsed_data.get('phone_number')

    # ---------------------------------------------------------
    # AGENT ASSIGNMENT LOGIC (ROUND ROBIN)
    # ---------------------------------------------------------
    assigned_user_id = None
    try:
        # 1. Get all active users (users) for this Admin
        from app.models import User 
        
        active_agents = User.query.filter_by(
            admin_id=fb_page.admin_id, 
            status='active',
            is_suspended=False
        ).order_by(User.id).all()

        if active_agents:
            # 2. Find the last assigned lead for this admin to determine sequence
            last_lead = Lead.query.filter_by(admin_id=fb_page.admin_id)\
                .filter(Lead.assigned_to.isnot(None))\
                .order_by(Lead.created_at.desc())\
                .first()

            if not last_lead or not last_lead.assigned_to:
                # No previous assignment, assign to first agent
                assigned_user_id = active_agents[0].id
            else:
                # Find index of last agent
                last_agent_id = last_lead.assigned_to
                
                # Check if last agent is still in the active list
                agent_ids = [agent.id for agent in active_agents]
                
                if last_agent_id in agent_ids:
                    current_index = agent_ids.index(last_agent_id)
                    next_index = (current_index + 1) % len(agent_ids)
                    assigned_user_id = agent_ids[next_index]
                else:
                    # Last agent removed/inactive, start over
                    assigned_user_id = agent_ids[0]
            
            current_app.logger.info(f"Assigning Lead to Agent ID: {assigned_user_id}")
        else:
            current_app.logger.warning("No active agents found for assignment.")

    except Exception as e:
        current_app.logger.error(f"Error in assignment logic: {e}")
        # Continue saving lead even if assignment fails

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
        assigned_to=assigned_user_id,
        custom_fields=parsed_data
    )
    
    db.session.add(new_lead)
    db.session.commit()
    current_app.logger.info(f"Lead saved successfully: {name} ({phone}) -> Assigned to: {assigned_user_id}")


# --- Add this new POST route for manual lead creation ---
@bp.route('/api/facebook/leads', methods=['POST'])
@jwt_required()
def create_manual_lead():
    try:
        claims = get_jwt()
        role = claims.get("role")
        current_identity = int(get_jwt_identity())

        # Strict Restriction: Only Users (Agents) can create manual leads
        if role != "user":
             return jsonify({'error': 'Only Agents can create manual leads'}), 403

        user = User.query.get(current_identity)
        if not user:
             return jsonify({'error': 'User not found'}), 404
        
        admin_id = user.admin_id

        data = request.get_json()
        
        # Check if lead exists for this admin
        existing_lead = Lead.query.filter_by(phone=data.get('phone'), admin_id=admin_id).first()
        if existing_lead:
            # Optionally update the existing lead or just return
            return jsonify({'message': 'Lead already exists', 'id': existing_lead.id}), 200

        # Map custom fields
        custom_data = data.get('custom_fields', {})
        
        # Create new lead
        new_lead = Lead(
            admin_id=admin_id,
            name=data.get('name'),
            phone=data.get('phone'),
            status=data.get('status', 'new'),
            source=data.get('source', 'call_history'),
            custom_fields=custom_data,
            created_at=now()
        )
        
        # Auto-assign to the creating agent
        new_lead.assigned_to = current_identity

        db.session.add(new_lead)
        db.session.commit()
        return jsonify({'message': 'Lead created', 'id': new_lead.id}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating manual lead: {e}")
        return jsonify({'error': str(e)}), 500
