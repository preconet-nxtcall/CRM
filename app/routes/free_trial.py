from flask import Blueprint, request, jsonify
from app.models import db, FreeTrial, Admin
from sqlalchemy import text

bp = Blueprint("free_trial", __name__)

@bp.route("/api/free-trial", methods=["POST"])
def create_free_trial():
    data = request.get_json()
    
    name = data.get("name")
    work_email = data.get("work_email")
    company_name = data.get("company_name")
    phone_number = data.get("phone_number")
    
    if not all([name, work_email, company_name, phone_number]):
        return jsonify({"error": "All fields are required"}), 400

    # 1. Check uniqueness in Admin table (Existing Accounts)
    if Admin.query.filter_by(email=work_email).first():
        return jsonify({"error": "Account already exists with this email"}), 400
        
    # Check for duplicates
    existing_phone = FreeTrial.query.filter_by(phone_number=phone_number).first()
    existing_email = FreeTrial.query.filter_by(work_email=work_email).first()

    if existing_phone and existing_email:
        return jsonify({"error": "Already exists your account"}), 400
    if existing_phone:
        return jsonify({"error": "Already exists this phone number"}), 400
    if existing_email:
         return jsonify({"error": "Already exists this email"}), 400

    try:
        new_trial = FreeTrial(
            name=name,
            work_email=work_email,
            company_name=company_name,
            phone_number=phone_number
        )
        db.session.add(new_trial)
        db.session.commit()
        
        # In a real app, send email here
        print(f"📧 Sending Free Trial email to {work_email}")
        
        return jsonify({"message": "Free trial request submitted successfully"}), 201
        
    except Exception as e:
        print(f"Error creating free trial: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to submit request"}), 500

@bp.route("/api/superadmin/free-trials", methods=["GET"])
def get_free_trials():
    # Basic protection - rely on Global Guard or check token manually if needed
    # The Global Guard in __init__.py should cover /api routes if configured, 
    # ensuring at least a valid token is present.
    try:
        trials = FreeTrial.query.order_by(FreeTrial.created_at.desc()).all()
        return jsonify([t.to_dict() for t in trials]), 200
    except Exception as e:
        print(f"Error fetching free trials: {e}")
        return jsonify({"error": "Failed to fetch records"}), 500

@bp.route("/api/superadmin/free-trials/<int:trial_id>/block", methods=["POST"])
def toggle_block_trial(trial_id):
    # Verify Super Admin here if not global (assuming global guard or handling it)
    try:
        trial = FreeTrial.query.get(trial_id)
        if not trial:
            return jsonify({"error": "Trial not found"}), 404
        
        data = request.get_json() or {}
        # If 'action' is provided, use it (block/unblock), else toggle
        action = data.get("action")
        
        if action == "block":
            trial.status = "blocked"
        elif action == "unblock":
            # Revert to active (expiration logic will handle display)
            trial.status = "active"
        else:
             # Toggle
             trial.status = "blocked" if trial.status != "blocked" else "active"
             
        db.session.commit()
        return jsonify({
            "message": f"Trial {'blocked' if trial.status == 'blocked' else 'activated'} successfully",
            "trial": trial.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Error blocking trial {trial_id}: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to update status"}), 500

@bp.route("/api/debug/migrate-db", methods=["GET"])
def migrate_db_schema():
    try:
        # Attempt to add the status column.
        # Note: This might fail if column exists, but that's fine (we catch exception).
        # We use a generic SQL command that works on Postgres and SQLite for adding columns.
        db.session.execute(text("ALTER TABLE free_trials ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
        db.session.commit()
        return jsonify({"message": "Migration successful: 'status' column added to 'free_trials' table."}), 200
    except Exception as e:
        db.session.rollback()
        # Check if error is 'column already exists'
        err_msg = str(e).lower()
        if "duplicate column" in err_msg or "already exists" in err_msg:
             return jsonify({"message": "Column 'status' already exists."}), 200
             
        return jsonify({"error": f"Migration failed: {str(e)}"}), 500
