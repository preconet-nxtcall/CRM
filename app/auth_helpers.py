from flask import jsonify, current_app
from flask_jwt_extended import get_jwt_identity
from app.models import User, Admin
from datetime import datetime, timezone

def get_authorized_user():
    """
    Fetch user from JWT and ensure:
      1. User exists and is active
      2. Parent Admin exists, is active, and is NOT EXPIRED
    Returns (user, response_tuple).
    If response_tuple is None, user is valid.
    Otherwise, return response_tuple.
    """
    try:
        user_id = int(get_jwt_identity())
    except:
        return None, (jsonify({"error": "Invalid token"}), 401)

    user = User.query.get(user_id)
    if not user:
        return None, (jsonify({"error": "User not found"}), 404)

    if not user.is_active:
        return None, (jsonify({"error": "Account deactivated"}), 403)
        
    # Check Blocked/Suspended
    if getattr(user, 'status', 'active') == 'blocked' or getattr(user, 'is_suspended', False):
         return None, (jsonify({"error": "Your account has been blocked/suspended by Admin."}), 403)

    # Session Check (Single Device Login)
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    token_session_id = claims.get("session_id")
    
    # If token has session_id, it MUST match DB. 
    # If token has NO session_id (old token), fail if DB has one.
    # If DB has NO session_id (logged out), fail (unless token is also None, but token exists).
    
    # Strict mode:
    # This handles:
    # 1. New Login logic (token=A, DB=A) -> Match
    # 2. Logout (token=A, DB=None) -> Mismatch -> Fail (Correct)
    # 3. New Login elsewhere (token=A, DB=B) -> Mismatch -> Fail (Correct)
    if token_session_id != user.current_session_id:
        return None, (jsonify({"error": "Session expired or logged in on another device"}), 401)

    # Check Admin Status
    admin = Admin.query.get(user.admin_id)
    if not admin:
        # It's possible the user has no admin if they are super_admin or something else, 
        # but the request implies standard users under admins.
        # If user.admin_id is nullable? Model says nullable=False.
        return None, (jsonify({"error": "Admin account missing"}), 403)

    if not admin.is_active:
        return None, (jsonify({"error": "Admin account deactivated"}), 403)
        
    # Expiry Check
    if admin.expiry_date:
        try:
            today = datetime.now(timezone.utc).date()
            # If expiry_date is datetime, get date()
            expiry_val = admin.expiry_date
            if isinstance(expiry_val, datetime):
                expiry_val = expiry_val.date()
                
            if expiry_val < today:
                return None, (jsonify({"error": "Admin subscription expired"}), 403)
        except Exception as e:
            current_app.logger.error(f"Expiry check error: {e}")
            return None, (jsonify({"error": "Authorization check failed"}), 500)

    return user, None
