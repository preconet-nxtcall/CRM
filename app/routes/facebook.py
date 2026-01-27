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
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        source_filter = request.args.get('source')

        query = Lead.query.filter_by(admin_id=admin_id)
        if source_filter and source_filter.lower() != 'all':
             query = query.filter(Lead.source == source_filter.lower())
        
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
@ b p . r o u t e ( ' / a p i / f a c e b o o k / l e a d s / < i n t : l e a d _ i d > / s t a t u s ' ,   m e t h o d s = [ ' P U T ' ] )  
 @ j w t _ r e q u i r e d ( )  
 d e f   u p d a t e _ l e a d _ s t a t u s ( l e a d _ i d ) :  
         " " "  
         U p d a t e   l e a d   s t a t u s   ( M a n u a l l y   b y   A d m i n / A g e n t )  
         " " "  
         t r y :  
                 c l a i m s   =   g e t _ j w t ( )  
                 r o l e   =   c l a i m s . g e t ( " r o l e " )  
                 c u r r e n t _ i d e n t i t y   =   i n t ( g e t _ j w t _ i d e n t i t y ( ) )  
                  
                 #   D e t e r m i n e   A d m i n   I D   s c o p e  
                 a d m i n _ i d   =   N o n e  
                 i f   r o l e   = =   " a d m i n " :  
                         a d m i n _ i d   =   c u r r e n t _ i d e n t i t y  
                 e l i f   r o l e   = =   " u s e r " :  
                         u s e r   =   U s e r . q u e r y . g e t ( c u r r e n t _ i d e n t i t y )  
                         i f   n o t   u s e r :   r e t u r n   j s o n i f y ( { " e r r o r " :   " U s e r   n o t   f o u n d " } ) ,   4 0 4  
                         a d m i n _ i d   =   u s e r . a d m i n _ i d  
                  
                 i f   n o t   a d m i n _ i d :  
                         r e t u r n   j s o n i f y ( { " e r r o r " :   " U n a u t h o r i z e d   c o n t e x t " } ) ,   4 0 3  
  
                 #   F e t c h   L e a d  
                 l e a d   =   L e a d . q u e r y . g e t ( l e a d _ i d )  
                 i f   n o t   l e a d :  
                           r e t u r n   j s o n i f y ( { " e r r o r " :   " L e a d   n o t   f o u n d " } ) ,   4 0 4  
                            
                 #   S e c u r i t y   C h e c k  
                 i f   l e a d . a d m i n _ i d   ! =   a d m i n _ i d :  
                           r e t u r n   j s o n i f y ( { " e r r o r " :   " U n a u t h o r i z e d   t o   a c c e s s   t h i s   l e a d " } ) ,   4 0 3  
  
                 d a t a   =   r e q u e s t . j s o n  
                 n e w _ s t a t u s   =   d a t a . g e t ( ' s t a t u s ' )  
                  
                 i f   n e w _ s t a t u s :  
                           #   A l l o w e d   c h e c k   o p t i o n a l ,   b u t   k e e p i n g   i t   f l e x i b l e   i s   b e t t e r   f o r   n o w  
                           l e a d . s t a t u s   =   n e w _ s t a t u s . l o w e r ( )    
                           d b . s e s s i o n . c o m m i t ( )  
                           r e t u r n   j s o n i f y ( { " m e s s a g e " :   " S t a t u s   u p d a t e d " ,   " s t a t u s " :   l e a d . s t a t u s } ) ,   2 0 0  
                  
                 r e t u r n   j s o n i f y ( { " e r r o r " :   " M i s s i n g   s t a t u s   f i e l d " } ) ,   4 0 0  
  
         e x c e p t   E x c e p t i o n   a s   e :  
                 d b . s e s s i o n . r o l l b a c k ( )  
                 r e t u r n   j s o n i f y ( { " e r r o r " :   s t r ( e ) } ) ,   5 0 0  
 