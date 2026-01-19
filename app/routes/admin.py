# admin.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, create_access_token, get_jwt_identity, get_jwt
from datetime import datetime, timezone, timedelta
from ..models import db, Admin, User, Attendance, CallHistory, ActivityLog, UserRole
import re
from sqlalchemy import func

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# -------------------------
# Helpers
# -------------------------
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

def validate_email(email: str) -> bool:
    return bool(email and EMAIL_PATTERN.match(email))

# =========================================================
# DEBUG EMAIL (Temporary)
# =========================================================
@bp.route("/debug-email", methods=["POST"])
@jwt_required()
def debug_email():
    """
    Test email sending and return RAW error if it fails.
    """
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403

    data = request.get_json() or {}
    to_email = data.get("email")
    
    if not to_email:
        return jsonify({"error": "email required"}), 400

    try:
        import requests
        
        api_token = current_app.config.get("ZEPTOMAIL_API_TOKEN")
        sender_email = current_app.config.get("ZEPTOMAIL_USER")
        
        if not api_token or not sender_email:
            return jsonify({"error": "Missing ZEPTOMAIL credentials in .env"}), 500

        url = "https://api.zeptomail.in/v1.1/email"
        subject = "Test Email from Call Manager Debugger (HTTP API)"
        html_content = "<h1>It Works!</h1><p>Your email configuration is correct using ZeptoMail HTTP API.</p>"
        
        payload = {
            "from": {
                "address": sender_email
            },
            "to": [{
                "email_address": {
                    "address": to_email,
                    "name": to_email.split('@')[0]
                }
            }],
            "subject": subject,
            "htmlbody": html_content
        }
        
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": api_token
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if response.status_code in [200, 201]:
            return jsonify({"message": f"Email successfully sent to {to_email}", "request_id": response.json().get("request_id")}), 200
        else:
            return jsonify({
                "error": "Email Failed",
                "details": response.text,
                "status_code": response.status_code
            }), 500

    except Exception as e:
        import traceback
        return jsonify({
            "error": "Email Failed",
            "details": str(e),
            "type": type(e).__name__,
            "trace": traceback.format_exc()
        }), 500

def iso(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    # ensure timezone-aware if possible
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return str(dt)

def is_online(dt):
    """
    Returns True if dt is within the last 5 minutes.
    """
    if not dt:
        return False
    
    # Ensure dt is timezone-aware (UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        
    now = datetime.now(timezone.utc)
    diff = now - dt
    return diff < timedelta(minutes=5)

def admin_required():
    claims = get_jwt()
    return claims.get("role") == "admin"

def get_admin_or_401():
    """
    Fetch admin from JWT identity and check active/expiry.
    Returns (admin, response) where response is None when OK, otherwise a Flask response tuple.
    """
    try:
        admin_id = int(get_jwt_identity())
    except Exception:
        return None, (jsonify({"error": "Invalid token identity"}), 401)

    admin = Admin.query.get(admin_id)
    if not admin:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if not admin.is_active:
        return None, (jsonify({"error": "Account deactivated"}), 403)
    if callable(getattr(admin, "is_expired", None)) and admin.is_expired():
        return None, (jsonify({"error": "Account expired"}), 403)
    return admin, None

def paginate_query(query, serialize_fn):
    """
    Generic pagination helper. Reads ?page & ?per_page from request.
    """
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get("per_page", 25))
    except ValueError:
        per_page = 25
    per_page = max(1, min(per_page, 1000))  # bound per_page

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = [serialize_fn(item) for item in pagination.items]
    meta = {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }
    return items, meta

def calculate_performance_for_user(user_id):
    """
    Example heuristic for performance_score:
      - attendance punctuality: % of on-time check-ins (status == 'on-time') * 0.6
      - call responsiveness: fraction of outgoing calls answered (duration > 0) * 0.4
    Returns a rounded 0-100 score.
    Adjust this function to match your desired business logic.
    """
    # attendance punctuality
    total_att = db.session.query(func.count(Attendance.id)).filter(Attendance.user_id == user_id).scalar() or 0
    ontime_att = db.session.query(func.count(Attendance.id)).filter(
        Attendance.user_id == user_id, Attendance.status == "on-time"
    ).scalar() or 0

    att_score = (ontime_att / total_att * 100) if total_att else 0

    # call responsiveness
    total_calls = db.session.query(func.count(CallHistory.id)).filter(CallHistory.user_id == user_id).scalar() or 0
    answered_calls = db.session.query(func.count(CallHistory.id)).filter(
        CallHistory.user_id == user_id, CallHistory.duration > 0
    ).scalar() or 0

    call_score = (answered_calls / total_calls * 100) if total_calls else 0

    # combine
    combined = (att_score * 0.6) + (call_score * 0.4)
    return round(combined, 2)


# -------------------------
# ADMIN LOGIN (unchanged mostly)
# -------------------------
@bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json() or {}
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "email and password are required"}), 400

        admin = Admin.query.filter(func.lower(Admin.email) == func.lower(email)).first()

        if not admin or not admin.check_password(password):
            return jsonify({"error": "Invalid credentials"}), 401

        if not admin.is_active:
            return jsonify({"error": "Account deactivated"}), 403

        if callable(getattr(admin, "is_expired", None)) and admin.is_expired():
            return jsonify({"error": "Account expired"}), 403


        admin.last_login = datetime.now(timezone.utc)
        
        # Session Management
        import uuid
        # Session Management
        import uuid
        session_id = uuid.uuid4().hex
        
        try:
            admin.current_session_id = session_id
            db.session.commit()
        except:
             db.session.rollback()
             return jsonify({"error": "Login failed (Session Save Error)"}), 500

        # LOGGING (Added for Recent Activity)
        try:
            log = ActivityLog(
                actor_role=UserRole.ADMIN,
                actor_id=admin.id,
                action="Logged in",  # Simple action text
                target_type="admin",
                target_id=admin.id
            )
            db.session.add(log)
            db.session.commit()
        except Exception as log_error:
            # Don't fail the login if logging fails
            current_app.logger.warning(f"Failed to log admin login: {log_error}")

        token = create_access_token(
            identity=str(admin.id),
            expires_delta=timedelta(days=365), # Long-lived token; rely on guard for revocation
            additional_claims={
                "role": "admin",
                "session_id": session_id
            }
        )

        return jsonify({
            "access_token": token,
            "user": {
                "id": admin.id,
                "name": admin.name,
                "email": admin.email,
                "role": "admin",
                "user_limit": getattr(admin, "user_limit", None),
                "expiry_date": iso(getattr(admin, "expiry_date", None))
            }
        }), 200

    except Exception as e:
        current_app.logger.exception("Admin login error")
        return jsonify({"error": "Internal server error"}), 500


# -------------------------
# ADMIN LOGOUT
# -------------------------
@bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    try:
        identity = get_jwt_identity()
        admin = Admin.query.get(int(identity))
        if admin:
            # Clear session to invalidate current token
            admin.current_session_id = None
            db.session.commit()
            
            # Log logout
            try:
                log = ActivityLog(
                    actor_role=UserRole.ADMIN,
                    actor_id=admin.id,
                    action="Logged out",
                    target_type="admin",
                    target_id=admin.id
                )
                db.session.add(log)
                db.session.commit()
            except:
                pass

        return jsonify({"message": "Logged out successfully"}), 200
    except Exception as e:
        return jsonify({"error": "Internal server error"}), 500


# -------------------------
# CREATE USER (secure & transactional)
# -------------------------
@bp.route("/create-user", methods=["POST"])
@jwt_required()
def create_user():
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403

    admin, resp = get_admin_or_401()
    if resp:
        return resp

    try:
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password")
        phone = data.get("phone")

        if not name or not email or not password:
            return jsonify({"error": "name, email and password are required"}), 400

        if not validate_email(email):
            return jsonify({"error": "Invalid email format"}), 400

        # Check limits
        current_count = User.query.filter_by(admin_id=admin.id).count()
        limit = getattr(admin, "user_limit", 10)
        if current_count >= limit:
            return jsonify({"error": f"User limit reached ({limit})"}), 403

        # Check existing under THIS admin
        existing_email = User.query.filter(User.admin_id == admin.id, func.lower(User.email) == email).first()
        existing_phone = User.query.filter(User.admin_id == admin.id, User.phone == phone).first()

        if existing_email:
             return jsonify({"error": "This email is already registered under your admin account."}), 409
        if existing_phone:
             return jsonify({"error": "This phone number is already registered under your admin account."}), 409
        
        # Note: We allow same email under DIFFERENT admin as per requirements.
        # But ensure unique constraint in DB doesn't block it if it exists globally.
        # Assuming DB constraint is (admin_id, email) unique, not just email unique.
        # If DB has global unique email, this might still fail if email exists for another admin.
        # Given the requirements, we proceed assuming schema supports it or we only care about this check.

        user = User(
            admin_id=admin.id,
            name=name,
            email=email,
            phone=phone,
            is_active=True
        )
        user.set_password(password)

        # Audit Log
        log = ActivityLog(
            actor_role=UserRole.ADMIN,
            actor_id=admin.id,
            action=f"Created user {email}",
            target_type="user"
        )

        db.session.add(user)
        # flush to get user.id for log target_id
        db.session.flush()
        log.target_id = user.id
        db.session.add(log)
        db.session.commit()

        # Automatic Notification
        try:
            from app.services.notification_service import NotificationService
            import logging
            
            logging.info(f"Attempting to send welcome email to {email}")
            result = NotificationService.send_welcome_notification(
                name=name,
                username=email,
                password=password,
                expiry_date=admin.expiry_date,
                phone=phone,
                email=email
            )
            if result:
                logging.info(f"Welcome email sent successfully to {email}")
            else:
                logging.warning(f"Welcome email failed to send to {email} - check ZEPTOMAIL credentials")
        except Exception as e:
            # Catch ALL errors so we never fail the request after DB commit
            import traceback
            traceback.print_exc()
            try:
                logging.error(f"CRITICAL: Failed to send notification to {email}: {e}", exc_info=True)
            except:
                print(f"CRITICAL: Failed to send notification to {email}: {e}")

        return jsonify({"message": "User created", "user_id": user.id}), 201

    except Exception as e:
        db.session.rollback()
        err_msg = str(e).lower()
        if "integrityerror" in err_msg and "email" in err_msg:
             return jsonify({"error": "Email globally exists. Run the Database Fix Tool (Super Admin) to allow duplicates."}), 409
        
        current_app.logger.exception("Create user failed")
        # Return actual error for debugging purposes instead of generic message
        return jsonify({"error": f"Server Error: {str(e)}"}), 500


# -------------------------
# GET ALL USERS (with pagination)
# -------------------------
@bp.route("/users", methods=["GET"])
@jwt_required()
def get_users():
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403

    admin, resp = get_admin_or_401()
    if resp:
        return resp

    try:
        query = User.query.filter_by(admin_id=admin.id)

        # Search filter
        search = request.args.get("search", "").strip()
        if search:
            term = f"%{search}%"
            query = query.filter(
                (User.name.ilike(term)) | (User.email.ilike(term))
            )

        # Status filter
        status = request.args.get("status", "all")
        if status == "active":
            query = query.filter(User.is_active == True)
        elif status == "inactive":
            query = query.filter(User.is_active == False)

        query = query.order_by(User.created_at.desc())

        def serialize(u):
            # Calculate performance score if missing
            score = getattr(u, "performance_score", None)
            if score is None or score == 0:
                score = calculate_performance_for_user(u.id)

            # Determine "Online Status" based on TODAY'S attendance
            # 1. Get today's attendance record for this user
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            
            todays_attendance = (
               Attendance.query.filter(
                   Attendance.user_id == u.id, 
                   Attendance.check_in >= today_start
               )
               .order_by(Attendance.check_in.desc())
               .first()
            )

            # 2. Logic:
            # - If checked_in but NOT checked_out -> "Active"
            # - If checked_out -> "Inactive"
            # - If no record -> "Inactive"
            
            attendance_status = "Inactive"
            if todays_attendance:
                if todays_attendance.check_in and not todays_attendance.check_out:
                    attendance_status = "Active"
                
            return {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "phone": u.phone,
                "is_active": u.is_active, # Account status
                "attendance_status": attendance_status, # Today's Check-in status
                "performance_score": score,
                "created_at": iso(getattr(u, "created_at", None)),
                "last_login": iso(getattr(u, "last_login", None)),
                "last_sync": iso(getattr(u, "last_sync", None)),
                "has_sync_data": bool(getattr(u, "last_sync", None))
            }

        items, meta = paginate_query(query, serialize)
        return jsonify({"users": items, "meta": meta}), 200

    except Exception as e:
        current_app.logger.exception("Get users failed")
        return jsonify({"error": "Internal server error"}), 500


# -------------------------
# USER CALL HISTORY (ownership checked + pagination)
# -------------------------
@bp.route("/user-call-history/<int:user_id>", methods=["GET"])
@jwt_required()
def user_call_history(user_id):
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403

    admin, resp = get_admin_or_401()
    if resp:
        return resp

    # Ownership check
    user = User.query.get(user_id)
    if not user or user.admin_id != admin.id:
        return jsonify({"error": "Unauthorized user access"}), 403

    try:
        q = CallHistory.query.filter_by(user_id=user_id).order_by(CallHistory.timestamp.desc())

        def serialize(c):
            return {
                "id": c.id,
                "number": c.phone_number, # FIXED: was c.number
                "call_type": c.call_type,
                "timestamp": iso(getattr(c, "timestamp", None)),
                "duration": c.duration,
                "name": c.contact_name, # FIXED: was c.name
                "created_at": iso(getattr(c, "created_at", None))
            }

        items, meta = paginate_query(q, serialize)
        return jsonify({"call_history": items, "meta": meta}), 200

    except Exception as e:
        current_app.logger.exception("User call history failed")
        return jsonify({"error": "Internal server error"}), 500


# -------------------------
# USER ATTENDANCE FULL LIST (ownership checked + pagination)
# -------------------------
@bp.route("/user-attendance/<int:user_id>", methods=["GET"])
@jwt_required()
def user_attendance(user_id):
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403

    admin, resp = get_admin_or_401()
    if resp:
        return resp

    user = User.query.get(user_id)
    if not user or user.admin_id != admin.id:
        return jsonify({"error": "Unauthorized user access"}), 403

    try:
        q = Attendance.query.filter_by(user_id=user_id).order_by(Attendance.created_at.desc())

        def serialize(a):
            return {
                "id": a.id,
                "user_id": a.user_id,
                "check_in": iso(getattr(a, "check_in", None)),
                "check_out": iso(getattr(a, "check_out", None)),
                "status": a.status,
                "address": a.address,
                "created_at": iso(getattr(a, "created_at", None))
            }

        items, meta = paginate_query(q, serialize)
        return jsonify({"attendance": items, "meta": meta}), 200

    except Exception as e:
        current_app.logger.exception("User attendance failed")
        return jsonify({"error": "Internal server error"}), 500


# -------------------------
# USER ANALYTICS (new feature)
# -------------------------
@bp.route("/user-analytics/<int:user_id>", methods=["GET"])
@jwt_required()
def user_analytics(user_id):
    """
    Returns analytics for a user:
      - total_calls, answered_calls, avg_call_duration
      - total_attendance, on_time_rate
      - last_sync, last_login
      - computed performance_score (and breakdown)
    """
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403

    admin, resp = get_admin_or_401()
    if resp:
        return resp

    user = User.query.get(user_id)
    if not user or user.admin_id != admin.id:
        return jsonify({"error": "Unauthorized user access"}), 403

    try:
        # Calls
        # Calls
        try:
            total_calls = CallHistory.query.filter_by(user_id=user_id).count()
            answered_calls = CallHistory.query.filter(CallHistory.user_id == user_id, CallHistory.duration > 0).count()
            avg_duration_res = db.session.query(func.avg(CallHistory.duration)).filter(CallHistory.user_id == user_id).scalar()
            avg_duration = float(avg_duration_res or 0.0)
        except Exception as e:
            current_app.logger.error(f"Error calculating call stats for user {user_id}: {e}")
            total_calls = 0
            answered_calls = 0
            avg_duration = 0.0

        # Attendance
        try:
            total_att = Attendance.query.filter_by(user_id=user_id).count()
            on_time = Attendance.query.filter_by(user_id=user_id, status="on-time").count()
            on_time_rate = round((on_time / total_att) * 100, 2) if total_att else 0.0
        except Exception as e:
            current_app.logger.error(f"Error calculating attendance stats for user {user_id}: {e}")
            total_att = 0
            on_time = 0
            on_time_rate = 0.0

        # last sync & login
        last_sync = getattr(user, "last_sync", None)
        last_login = getattr(user, "last_login", None)

        # computed performance
        try:
            perf_score = calculate_performance_for_user(user_id)
        except Exception as e:
            current_app.logger.error(f"Error calculating performance for user {user_id}: {e}")
            perf_score = 0

        analytics = {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone
            },
            "calls": {
                "total_calls": total_calls,
                "answered_calls": answered_calls,
                "avg_duration_seconds": round(avg_duration, 2)
            },
            "attendance": {
                "total_attendance": total_att,
                "on_time_count": on_time,
                "on_time_rate_percent": on_time_rate
            },
            "last_sync": iso(last_sync),
            "last_login": iso(last_login),
            "performance": {
                "score": perf_score,
                "method": "attendance(60%) + calls(40%) heuristic"
            }
        }

        return jsonify({"analytics": analytics}), 200

    except Exception as e:
        current_app.logger.exception("User analytics failed")
        return jsonify({"error": "Internal server error"}), 500


# -------------------------
# DASHBOARD STATS (MOVED TO admin_dashboard.py)
# -------------------------
# @bp.route("/dashboard-stats", methods=["GET"])
# @jwt_required()
# def dashboard_stats():
#     return jsonify({"error": "Use admin_dashboard_bp"}), 410


# -------------------------
# RECENT SYNC ACTIVITY
# -------------------------
@bp.route("/recent-sync", methods=["GET"])
@jwt_required()
def recent_sync():
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())
    
    # Get users with most recent last_sync
    recent_users = User.query.filter(
        User.admin_id == admin_id,
        User.last_sync.isnot(None)
    ).order_by(User.last_sync.desc()).limit(5).all()

    data = []
    for u in recent_users:
        data.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "last_sync": iso(u.last_sync),
            "time_ago": "Just now", # simplified, frontend can calc relative time
            "is_active": is_online(u.last_sync)
        })

    return jsonify({"recent_sync": data}), 200

# -------------------------
# USER LOGS (Recent Activity)
# -------------------------
@bp.route("/user-logs", methods=["GET"])
@jwt_required()
def user_logs():
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    admin_id = int(get_jwt_identity())

    # Define "today" in UTC
    now_utc = datetime.utcnow()
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    # Fetch TODAY's attendance events only
    logs = db.session.query(Attendance, User).join(User).filter(
        User.admin_id == admin_id,
        Attendance.check_in >= today_start  # Only today's records
    ).order_by(Attendance.created_at.desc()).limit(10).all()

    data = []
    for att, user in logs:
        # Determine status based on check-in/check-out
        # If checked in but NOT checked out -> Active
        # If checked out -> Inactive
        if att.check_in and not att.check_out:
            status = "Active"
            is_active = True
        else:
            status = "Inactive"
            is_active = False
            
        data.append({
            "id": att.id,
            "user_name": user.name,
            "action": f"Status: {status}",
            "timestamp": iso(att.check_in),  # Show check-in time
            "type": "attendance",
            "is_active": is_active
        })

    return jsonify({"logs": data}), 200


# =========================================================
# UPDATE USER (Full Edit including Password)
# =========================================================
@bp.route("/user/<int:user_id>", methods=["PUT"])
@jwt_required()
def update_user(user_id):
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403

    admin, resp = get_admin_or_401()
    if resp:
        return resp

    # Ownership Check
    user = User.query.get(user_id)
    if not user or user.admin_id != admin.id:
        return jsonify({"error": "Unauthorized user access"}), 403

    try:
        data = request.get_json() or {}
        
        # Only allow password updates
        if "password" not in data or not data["password"].strip():
            return jsonify({"error": "Password is required"}), 400

        # Update Password
        user.set_password(data["password"].strip())
        
        # Force logout/block old session on password change
        from app.models import gen_uuid
        user.current_session_id = gen_uuid()
        
        # Log password reset
        log = ActivityLog(
            actor_role=UserRole.ADMIN,
            actor_id=admin.id,
            action=f"Updated password for user {user.email}",
            target_type="user",
            target_id=user.id
        )
        db.session.add(log)

        db.session.commit()

        return jsonify({
            "message": "User updated successfully",
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Update user failed")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500


# =========================================================
# DELETE USER
# =========================================================
@bp.route("/user/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403

    admin, resp = get_admin_or_401()
    if resp:
        return resp

    # Ownership Check
    user = User.query.get(user_id)
    if not user or user.admin_id != admin.id:
        return jsonify({"error": "Unauthorized user access"}), 403

    try:
        user_email = user.email

        # Delete User (Cascade should handle related data, but we can be explicit if needed)
        db.session.delete(user)
        
        # Log deletion
        log = ActivityLog(
            actor_role=UserRole.ADMIN,
            actor_id=admin.id,
            action=f"Deleted user {user_email}",
            target_type="user",
            target_id=user_id
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({"message": f"User {user_email} deleted successfully"}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Delete user failed")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500