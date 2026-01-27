from flask import Blueprint, request, jsonify, current_app, session, redirect
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import db, FacebookConnection, FacebookPage, Lead, Admin, User, now
import requests
import hmac
import hashlib
import sys
from app.services.facebook_service import FacebookService

bp = Blueprint('facebook', __name__)

# =======================================================
#  STRICT SERVER-SIDE OAUTH FLOW
# =======================================================

@bp.route('/api/facebook/auth/start', methods=['GET'])
@jwt_required()
def start_oauth():
    """
    Step 1: Generate Facebook Login URL.
    Frontend should redirect here or open this URL in a popup.
    """
    try:
        app_id = current_app.config.get('FACEBOOK_APP_ID')
        # Use a fixed callback URL that matches App Settings
        redirect_uri = f"{request.host_url.rstrip('/')}/api/facebook/auth/callback"
        
        # Store admin_id in state to verify later (optional security)
        state = get_jwt_identity()
        
        url = FacebookService.get_oauth_url(app_id, redirect_uri, state)
        return jsonify({"url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/facebook/auth/callback', methods=['GET'])
def oauth_callback():
    """
    Step 2: Facebook redirects back here with 'code'.
    We exchange it for a User Token and store it in SESSION.
    Frontend NEVER sees this token.
    """
    try:
        code = request.args.get('code')
        error = request.args.get('error')
        
        if error:
            return f"Facebook Auth Error: {error}", 400
            
        if not code:
            return "Missing code", 400

        app_id = current_app.config.get('FACEBOOK_APP_ID')
        app_secret = current_app.config.get('FACEBOOK_APP_SECRET')
        redirect_uri = f"{request.host_url.rstrip('/')}/api/facebook/auth/callback"

        # Exchange code for User Access Token
        user_token = FacebookService.exchange_code(code, app_id, app_secret, redirect_uri)
        
        # Store in Server-Side Session (Signed Cookie)
        session['fb_user_token'] = user_token
        
        # Close popup or redirect to frontend success page
        # Simple HTML to auto-close popup and notify parent window
        return """
        <script>
            if (window.opener) {
                window.opener.postMessage({ type: 'FB_AUTH_SUCCESS' }, '*');
                window.close();
            } else {
                document.write("Authentication Successful! You can close this window.");
            }
        </script>
        """
    except Exception as e:
        current_app.logger.error(f"OAuth Callback Failed: {e}")
        return f"Authentication Failed: {str(e)}", 500


# =======================================================
#  STRICT CONNECT ENDPOINT (NO TOKENS IN BODY)
# =======================================================

@bp.route('/api/facebook/pages', methods=['GET'])
@jwt_required()
def list_pages():
    """
    Step 2.5: List pages for the user to select.
    Uses Session Token.
    """
    try:
        user_token = session.get('fb_user_token')
        if not user_token:
            return jsonify({"error": "Session expired. Please login again."}), 401
            
        pages = FacebookService.get_user_pages(user_token)
        return jsonify({"pages": pages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@bp.route('/api/facebook/connect', methods=['POST'])
@jwt_required()
def connect_page():
    """
    Step 3: Admin selects a page to connect.
    Contract: Input = { page_id, page_name, page_access_token } ONLY.
    """
    try:
        current_identity = int(get_jwt_identity())
        admin = Admin.query.get(current_identity)
        if not admin:
            return jsonify({"error": "Admin required"}), 403

        # 1. Strict Input
        data = request.json
        page_id = data.get('page_id')
        page_name = data.get('page_name')
        page_access_token = data.get('page_access_token')
        
        if not page_id or not page_name or not page_access_token:
            return jsonify({"error": "Missing page_id, page_name, or page_access_token"}), 400

        app_id = current_app.config.get('FACEBOOK_APP_ID')
        app_secret = current_app.config.get('FACEBOOK_APP_SECRET')

        # 2. Exchange for Long-Lived Token (60 days)
        current_app.logger.info(f"Exchanging token for page: {page_id}")
        long_lived_token = FacebookService.exchange_for_long_lived_token(
            page_access_token, 
            app_id, 
            app_secret
        )
        
        # 3. Subscribe Webhook
        sub_url = f"https://graph.facebook.com/v24.0/{page_id}/subscribed_apps"
        sub_resp = requests.post(sub_url, params={
            "access_token": long_lived_token, 
            "subscribed_fields": "leadgen"
        })
        
        if sub_resp.status_code != 200:
            current_app.logger.warning(f"Webhook subscription warning: {sub_resp.text}")

        # 4. Save to DB (Simplified Schema)
        conn = FacebookConnection.query.filter_by(admin_id=admin.id).first()
        if not conn:
            conn = FacebookConnection(admin_id=admin.id)
            
        conn.page_id = page_id
        conn.page_name = page_name
        conn.set_token(long_lived_token)  # Encrypts automatically
        conn.status = 'active'
        conn.updated_at = now()
        # Note: system_user_id and business_manager_id will be NULL for this flow
        
        db.session.add(conn)
        db.session.commit()
        
        # Clear session token (security)
        session.pop('fb_user_token', None)

        return jsonify({"message": "Connected successfully"}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Connect Failed: {e}")
        return jsonify({"error": str(e)}), 500



@bp.route('/api/facebook/status', methods=['GET'])
@jwt_required()
def get_status():
    try:
        current_identity = int(get_jwt_identity())
        # Check Admin
        if not Admin.query.get(current_identity):
             return jsonify({"error": "Admin required"}), 403

        conn = FacebookConnection.query.filter_by(admin_id=current_identity).first()
        
        if conn and conn.status == 'active':
            return jsonify({
                "connected": True,
                "page": {
                    "id": conn.page_id,
                    "name": conn.page_name
                }
            })
        
        return jsonify({"connected": False, "page": None})
    except Exception as e:
         return jsonify({"error": str(e)}), 500


@bp.route('/api/facebook/disconnect', methods=['POST'])
@jwt_required()
def disconnect():
    try:
        current_identity = int(get_jwt_identity())
        conn = FacebookConnection.query.filter_by(admin_id=current_identity).first()
        
        if conn:
            # Optionally revoke permissions via Graph API
            
            # Delete from DB
            db.session.delete(conn)
            db.session.commit()
            
        return jsonify({"message": "Disconnected"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =======================================================
#  LEAD RETRIEVAL & WEBHOOK
# =======================================================

@bp.route('/api/facebook/leads', methods=['GET'])
@jwt_required()
def get_leads():
    """
    Get all leads for the current Admin or Agent.
    Default: Shows today's records with 10 per page.
    """
    try:
        claims = get_jwt()
        role = claims.get("role")
        current_identity = int(get_jwt_identity())

        admin_id = None
        if role == "admin":
            admin_id = current_identity
        elif role == "user":
            user = User.query.get(current_identity)
            if not user: return jsonify({"error": "User not found"}), 404
            admin_id = user.admin_id
        
        # Pagination - default to 10 records per page
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        source_filter = request.args.get('source')
        date_filter = request.args.get('date_filter', 'today')  # today, week, month, all

        query = Lead.query.filter_by(admin_id=admin_id)
        
        # Apply source filter
        if source_filter and source_filter.lower() != 'all':
             query = query.filter(Lead.source == source_filter.lower())
        
        # Apply date filter - default to today's records
        # Apply date filter - default to today's records
        from datetime import datetime, timedelta
        if date_filter == 'today':
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            query = query.filter(Lead.created_at >= today_start, Lead.created_at < today_end)
        elif date_filter == 'week':
            week_start = datetime.now() - timedelta(days=7)
            query = query.filter(Lead.created_at >= week_start)
        elif date_filter == 'month':
            month_start = datetime.now() - timedelta(days=30)
            query = query.filter(Lead.created_at >= month_start)
        # 'all' means no date filter
        
        query = query.order_by(Lead.created_at.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        
        results = [l.to_dict() for l in paginated.items]
        
        return jsonify({
            "leads": results,
            "total": paginated.total,
            "pages": paginated.pages,
            "current_page": page
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/facebook/leads/<int:lead_id>/status', methods=['PUT'])
@jwt_required()
def update_lead_status(lead_id):
    """
    Update status for a specific lead.
    """
    try:
        claims = get_jwt()
        role = claims.get("role")
        current_identity = int(get_jwt_identity())
        
        # Admin or User Check
        admin_id = None
        if role == "admin":
            admin_id = current_identity
        elif role == "user":
            user = User.query.get(current_identity)
            if not user: return jsonify({"error": "User not found"}), 404
            admin_id = user.admin_id

        lead = Lead.query.get(lead_id)
        if not lead:
            return jsonify({"error": "Lead not found"}), 404

        # Verify access rights
        if lead.admin_id != admin_id:
             return jsonify({"error": "Unauthorized"}), 403

        data = request.json
        new_status = data.get('status')
        if not new_status:
            return jsonify({"error": "Status required"}), 400

        lead.status = new_status
        lead.updated_at = now()
        
        db.session.commit()
        
        return jsonify({
            "message": "Status updated successfully",
            "lead": lead.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Webhook Verification & Handling
@bp.route('/api/facebook/webhook', methods=['GET', 'POST'])
def handle_webhook():
    # 1. VERIFY (Get)
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == 'subscribe' and token == current_app.config.get('FACEBOOK_VERIFY_TOKEN'):
            return challenge, 200
        return 'Forbidden', 403

    # 2. INGEST (Post)
    if not verify_fb_signature(request):
        return "Invalid signature", 403

    data = request.json
    current_app.logger.info(f"WEBHOOK_DATA: {data}")

    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            page_id = entry.get('id')
            
            # Find Connection strictly by page_id (and ensuring active status)
            # Note: We query FacebookConnection directly now
            conn = FacebookConnection.query.filter_by(page_id=page_id, status='active').first()
            if not conn:
                current_app.logger.warning(f"Webhook received for unknown/inactive page {page_id}")
                continue

            for change in entry.get('changes', []):
                if change.get('field') == 'leadgen':
                    val = change.get('value', {})
                    lead_id = val.get('leadgen_id')
                    form_id = val.get('form_id')
                    
                    if not lead_id or lead_id.startswith("444"): # Example test ID filter
                        continue
                        
                    process_lead_strict(conn, lead_id, form_id)

        return 'EVENT_RECEIVED', 200
    
    return 'Not a Page Event', 404


def process_lead_strict(conn, lead_id, form_id):
    """
    Fetch lead using SYSTEM USER TOKEN (Strict Requirement).
    """
    # 1. Deduplicate
    existing = Lead.query.filter_by(facebook_lead_id=lead_id, admin_id=conn.admin_id).first()
    if existing: return

    # 2. Fetch from Graph API using Permanent System Token
    try:
        sys_token = conn.get_token() # Decrypts automatically
        url = f"https://graph.facebook.com/v24.0/{lead_id}"
        resp = requests.get(url, params={"access_token": sys_token})
        
        if resp.status_code != 200:
            current_app.logger.error(f"Lead Fetch Failed: {resp.text}")
            return
            
        lead_data = resp.json()
        
        # 3. Parse Data (Simplified for brevity, similar map logic as before)
        # ... (Parsing logic same as previous, just adapting to new context if needed)
        # For strict compliance, using basic field extraction:
        name = "Unknown"
        email = None
        phone = None
        
        for f in lead_data.get("field_data", []):
            if "name" in f.get("name"): name = f.get("values")[0]
            if "email" in f.get("name"): email = f.get("values")[0]
            if "phone" in f.get("name"): phone = f.get("values")[0]

        # 4. Assignment (Round Robin)
        assigned_to = None
        try:
            # Get active agents for this admin
            active_agents = User.query.filter_by(
                admin_id=conn.admin_id, 
                status='active',
                is_suspended=False
            ).order_by(User.id).all()

            if active_agents:
                # Find last assigned lead to determine sequence
                last_lead = Lead.query.filter_by(admin_id=conn.admin_id)\
                    .filter(Lead.assigned_to.isnot(None))\
                    .order_by(Lead.created_at.desc())\
                    .first()

                if not last_lead or not last_lead.assigned_to:
                    assigned_to = active_agents[0].id
                else:
                    last_agent_id = last_lead.assigned_to
                    agent_ids = [a.id for a in active_agents]
                    
                    if last_agent_id in agent_ids:
                        current_index = agent_ids.index(last_agent_id)
                        next_index = (current_index + 1) % len(agent_ids)
                        assigned_to = agent_ids[next_index]
                    else:
                        assigned_to = agent_ids[0]
                
                current_app.logger.info(f"Assigning Lead to Agent ID: {assigned_to}")
        except Exception as e:
            current_app.logger.error(f"Assignment Logic Failed: {e}")

        # 5. Save
        lead = Lead(
            admin_id=conn.admin_id,
            facebook_lead_id=lead_id,
            form_id=form_id,
            name=name,
            email=email,
            phone=phone,
            source="facebook",
            status="new",
            assigned_to=assigned_to
        )
        db.session.add(lead)
        db.session.commit()
        
    except Exception as e:
        current_app.logger.error(f"Process Lead Strict Error: {e}")

# Helper for sig check
def verify_fb_signature(req):
    signature = req.headers.get("X-Hub-Signature-256")
    app_secret = current_app.config.get("FACEBOOK_APP_SECRET")
    if not signature or not app_secret: return False
    expected = "sha256=" + hmac.new(app_secret.encode(), msg=req.data, digestmod=hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
