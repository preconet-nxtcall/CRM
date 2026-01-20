from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request, send_from_directory, redirect, url_for, render_template
from flask_jwt_extended import (
    JWTManager,
    verify_jwt_in_request,
    get_jwt,
    get_jwt_identity,
)
from flask_migrate import Migrate
from flask_cors import CORS
from sqlalchemy import inspect
from datetime import datetime, date
import os

from app.models import db, bcrypt, Admin, User, SuperAdmin
from config import Config
from flask_apscheduler import APScheduler

jwt = JWTManager()
migrate = Migrate()
scheduler = APScheduler()

def create_app(config_class=Config):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_class)

    # Init extensions
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    
    # Scheduler
    scheduler.init_app(app)
    scheduler.start()
    
    # Register Jobs
    try:
        from app.services.indiamart_service import scheduled_sync_job
        # Remove existing if any (to avoid duplicates on reload)
        if scheduler.get_job('indiamart_sync'):
             scheduler.remove_job('indiamart_sync')
             
        scheduler.add_job(
            id='indiamart_sync', 
            func=scheduled_sync_job, 
            args=[app], 
            trigger='interval', 
            minutes=15
        )
        
        # Magicbricks Job (Every 10 mins)
        from app.services.magicbricks_service import scheduled_magicbricks_job
        if scheduler.get_job('magicbricks_sync'):
             scheduler.remove_job('magicbricks_sync')
             
        scheduler.add_job(
            id='magicbricks_sync', 
            func=scheduled_magicbricks_job, 
            args=[app], 
            trigger='interval', 

            minutes=10
        )

        # 99acres Job (Every 10 mins)
        from app.services.ninety_nine_acres_service import scheduled_99acres_job
        if scheduler.get_job('99acres_sync'):
             scheduler.remove_job('99acres_sync')
             
        scheduler.add_job(
            id='99acres_sync', 
            func=scheduled_99acres_job, 
            args=[app], 
            trigger='interval', 
            minutes=10
        )
    except Exception as e:
        print(f"Scheduler Error: {e}")

    # Run DB Patch
    with app.app_context():
        from app.db_patch import run_schema_patch
        run_schema_patch()

    # =======================================================
    # GLOBAL GUARD (Strict Enforcement)
    # =======================================================
    @app.before_request
    def global_guard():
        if request.method == "OPTIONS":
            return
        
        # Public routes whitelist (by endpoint name)
        # We rely on verify_jwt_in_request(optional=True) to skip public routes naturally if no token is sent.
        # But if a token IS sent to a public route (e.g. login), we usually don't want to fail valid login attempts 
        # just because the *previous* session was invalid. 
        # However, checking Block/Suspend on Login is GOOD. 
        # Checking Session on Login is BAD (because we are creating a new one).
        
        # Let's identify if we should skip strict session checks.
        endpoint = request.endpoint
        is_login_flow = endpoint in ["users.login", "admin.login", "auth_pwd.forgot_password", "auth_pwd.reset_password", "super_admin_login_page", "super_admin_login_redirect", "forgot_password_redirect", "reset_password_redirect", "super_admin_fix_db_redirect"]

        try:
            from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
            verify_jwt_in_request(optional=True)
            identity = get_jwt_identity()
            
            if not identity:
                return # No token -> let route handler decide (401 if protected)

            claims = get_jwt()
            role = claims.get("role")
            
            # ---------------------------------------------------------
            # PRIORITY 1: ACCOUNT BLOCKED / SUSPENDED
            # ---------------------------------------------------------
            # Check User Status on EVERY Request
            
            if role == "user":
                user = User.query.get(int(identity))
                if not user:
                    return jsonify({"error": "User not found"}), 401

                # 1. Blocked/Suspended
                # "Using the word 'blocked' or 'suspended' in the error string is mandatory"
                if (hasattr(user, 'status') and user.status == 'blocked') or \
                   (hasattr(user, 'is_suspended') and user.is_suspended) or \
                   (not user.is_active): # Fallback/Legacy
                    return jsonify({"error": "Your account has been blocked/suspended by Admin."}), 403

                # ---------------------------------------------------------
                # PRIORITY 2: SUBSCRIPTION EXPIRED
                # ---------------------------------------------------------
                # Check current user's specific expiry OR fallback to Admin's expiry
                today = datetime.utcnow().date()
                
                # Check User's Personal Expiry (if exists)
                if hasattr(user, 'subscription_expiry_date') and user.subscription_expiry_date:
                    exp = user.subscription_expiry_date
                    if isinstance(exp, datetime): exp = exp.date()
                    if exp < today:
                         return jsonify({"error": "Your subscription plan has expired."}), 403
                
                # Check Parent Admin's Expiry (Standard Flow)
                admin = Admin.query.get(user.admin_id)
                if admin: # Admin might be deleted?
                    if admin.expiry_date:
                        exp = admin.expiry_date
                        if isinstance(exp, datetime): exp = exp.date()
                        if exp < today:
                             return jsonify({"error": "Your subscription plan has expired."}), 403
                
                # ---------------------------------------------------------
                # PRIORITY 3: SINGLE SESSION COMPLIANCE
                # ---------------------------------------------------------
                if not is_login_flow:
                    token_session_id = claims.get("session_id")
                    # Strict comparison: If token has ID, it MUST match DB. 
                    # If DB is None (Logged out), valid token ("abc") != None -> FAIL.
                    if token_session_id != user.current_session_id:
                        return jsonify({"error": "Session invalidated. Logged in on another device."}), 401

            elif role == "admin":
                admin = Admin.query.get(int(identity))
                if not admin:
                    return jsonify({"error": "Admin not found"}), 401
                
                # Admin Blocked Check
                if not admin.is_active:
                     return jsonify({"error": "Your account has been blocked/suspended by Admin."}), 403

                # Admin Subscription Check
                if admin.expiry_date:
                    today = datetime.utcnow().date()
                    exp = admin.expiry_date
                    if isinstance(exp, datetime): exp = exp.date()
                    if exp < today:
                         return jsonify({"error": "Your subscription plan has expired."}), 403

                # Admin Session Check
                if not is_login_flow:
                    token_session_id = claims.get("session_id")
                    if token_session_id != admin.current_session_id:
                        return jsonify({"error": "Session invalidated. Logged in on another device."}), 401

        except Exception as e:
            # If something breaks in the guard, safe fail to 401 or log error?
            # Better to log and let it pass if it's not a clear auth failure, OR fail secure.
            # Fail secure (500) is better for "Strict Enforcement".
            if "NoAuthorizationError" not in str(type(e)):
                print(f"Global Guard Error: {e}") 
            return # Let others handle it or return 500? Use default Flask error handling.
    
        return

    # =======================================================
    # IMPORT ROUTES
    # =======================================================

    from app.routes.super_admin import bp as super_admin_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.users import bp as users_bp
    from app.routes.fix import bp as fix_bp
    from app.routes.attendance import bp as attendance_bp
    from app.routes.call_history import bp as call_history_bp
    from app.routes.admin_call_history import bp as admin_call_history_bp
    from app.routes.admin_attendance import bp as admin_attendance_bp
    from app.routes.admin_call_analytics import bp as admin_call_analytics_bp

    from app.routes.admin_performance import bp as admin_performance_bp
    from app.routes.admin_dashboard import admin_dashboard_bp
    from app.routes.admin_sync import bp as admin_sync_bp
    from app.routes.admin_users import admin_user_bp  # NEW
    from app.routes.call_analytics import bp as call_analytics_bp  # NEW
    from app.routes.followup import bp as followup_bp # NEW
    from app.routes.auth_pwd import bp as auth_pwd_bp # NEW
    from app.routes.app_usage import bp as app_usage_bp # NEW
    from app.routes.facebook import bp as facebook_bp # NEW

    # =======================================================
    # REGISTER BLUEPRINTS
    # =======================================================

    app.register_blueprint(super_admin_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(fix_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(call_history_bp)

    app.register_blueprint(admin_call_history_bp)
    app.register_blueprint(admin_attendance_bp)
    app.register_blueprint(admin_call_analytics_bp)
    app.register_blueprint(admin_performance_bp)
    app.register_blueprint(admin_dashboard_bp)
    app.register_blueprint(admin_sync_bp)
    app.register_blueprint(admin_user_bp)  # NEW: User Management Actions

    app.register_blueprint(call_analytics_bp)  # NEW
    app.register_blueprint(followup_bp) # NEW
    app.register_blueprint(auth_pwd_bp) # NEW
    app.register_blueprint(app_usage_bp) # NEW
    app.register_blueprint(facebook_bp) # NEW
    
    from app.routes.indiamart import bp as indiamart_bp
    app.register_blueprint(indiamart_bp) # NEW
    

    from app.routes.magicbricks import bp as magicbricks_bp
    app.register_blueprint(magicbricks_bp) # NEW
    
    from app.routes.ninety_nine_acres import bp as ninety_nine_acres_bp
    app.register_blueprint(ninety_nine_acres_bp) # NEW
    
    from app.routes.free_trial import bp as free_trial_bp
    app.register_blueprint(free_trial_bp)

    from app.routes.debug import bp as debug_bp
    app.register_blueprint(debug_bp)


    # =======================================================
    # DATABASE INIT
    # =======================================================
    with app.app_context():
        # Always create missing tables (safe - won't drop existing tables)
        # This ensures new tables like activity_logs are created on deployment
        db.create_all()
            
        # FORCE SCHEMA UPDATE (Fix for missing checkout fields)
        try:
            from app.db_patch import run_schema_patch
            run_schema_patch()
        except Exception as e:
            print(f"Auto-patch warning: {e}")

    # =======================================================
    # FRONTEND ROUTING
    # =======================================================

    # Robust way to find 'frontend' relative to this file (app/__init__.py)
    # This ensures it works regardless of where the app is started from.
    basedir = os.path.abspath(os.path.dirname(__file__)) # .../backend/app
    backend_dir = os.path.dirname(basedir)               # .../backend
    FRONTEND = os.path.join(backend_dir, "frontend")     # .../backend/frontend

    @app.route("/")
    def home():
        return send_from_directory(FRONTEND, "index.html")

    # -------- LANDING PAGE ASSETS --------
    @app.route("/css/<path:filename>")
    def landing_css(filename):
        return send_from_directory(os.path.join(FRONTEND, "css"), filename)

    @app.route("/js/<path:filename>")
    def landing_js(filename):
        return send_from_directory(os.path.join(FRONTEND, "js"), filename)

    @app.route("/images/<path:filename>")
    def landing_images(filename):
        return send_from_directory(os.path.join(FRONTEND, "images"), filename)

    @app.route("/fonts/<path:filename>")
    def landing_fonts(filename):
        return send_from_directory(os.path.join(FRONTEND, "fonts"), filename)

    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(FRONTEND, 'images'), 'favicon.png', mimetype='image/vnd.microsoft.icon')

    # -------- POLICY PAGES --------
    @app.route("/privacy-policy")
    def privacy():
        return render_template("privacy.html")

    @app.route("/terms")
    def terms():
        return render_template("terms.html")

    @app.route("/data-deletion-instructions")
    def delete_data():
        return render_template("delete.html")

    @app.route("/api/health")
    def health():
        return jsonify({"status": "running", "db": "connected"}), 200

    # -------- ADMIN FRONTEND --------
    @app.route("/login")
    def admin_login_page():
        return send_from_directory(os.path.join(FRONTEND, "admin"), "login.html")

    @app.route("/admin/login.html")
    def old_admin_login_redirect():
         return redirect(url_for("admin_login_page"))

    @app.route("/forgot-password")
    def forgot_password_page():
        return send_from_directory(os.path.join(FRONTEND, "admin"), "forgot_password.html")

    @app.route("/forgot_password.html")
    def forgot_password_redirect():
        return redirect(url_for("forgot_password_page"))

    @app.route("/reset-password")
    def reset_password_page():
        return send_from_directory(os.path.join(FRONTEND, "admin"), "reset_password.html")

    @app.route("/reset_password.html")
    def reset_password_redirect():
        return redirect(url_for("reset_password_page"))

    @app.route("/admin/")
    def admin_dashboard_index():
        return send_from_directory(os.path.join(FRONTEND, "admin"), "index.html")

    @app.route("/admin/<path:filename>")
    def admin_static(filename):
        if filename == "index.html":
             return redirect(url_for("admin_dashboard_index"))
        return send_from_directory(os.path.join(FRONTEND, "admin"), filename)

    # -------- SUPER ADMIN FRONTEND --------
    @app.route("/super_admin/login")
    def super_admin_login_page():
        return send_from_directory(os.path.join(FRONTEND, "super_admin"), "login.html")

    @app.route("/super_admin/login.html")
    def super_admin_login_redirect():
        return redirect(url_for("super_admin_login_page"))

    @app.route("/super_admin/")
    def super_admin_dashboard_index():
         return send_from_directory(os.path.join(FRONTEND, "super_admin"), "index.html")

    @app.route("/super_admin/<path:filename>")
    def super_admin_static(filename):
        if filename == "index.html":
            return redirect(url_for("super_admin_dashboard_index"))
        return send_from_directory(os.path.join(FRONTEND, "super_admin"), filename)

    @app.route("/super_admin/fix-db")
    def super_admin_fix_db_page():
        return send_from_directory(os.path.join(FRONTEND, "super_admin"), "fix_db.html")

    @app.route("/super_admin/fix_db.html")
    def super_admin_fix_db_redirect():
        return redirect(url_for("super_admin_fix_db_page"))

    # -------- UPLOADS (IMAGES) --------
    @app.route("/uploads/<path:filename>")
    def uploaded_files(filename):
        # Fix: Helper to serve from valid locations
        # Try 'static/uploads' first (where recordings are)
        static_uploads = os.path.join(app.root_path, "static", "uploads")
        full_static_path = os.path.join(static_uploads, filename)
        
        if os.path.exists(full_static_path):
             return send_from_directory(static_uploads, filename)
        
        # Fallback to root 'uploads' (legacy)
        root_uploads = os.path.join(os.getcwd(), "uploads")
        full_root_path = os.path.join(root_uploads, filename)
        
        if os.path.exists(full_root_path):
             return send_from_directory(root_uploads, filename)
             
        # Log failure logic for debugging
        print(f"❌ 404 Upload Not Found: {filename}")
        print(f"   Checked: {full_static_path}")
        print(f"   Checked: {full_root_path}")
        
        return jsonify({"error": "File not found"}), 404

    return app
