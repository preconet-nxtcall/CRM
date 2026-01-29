from flask import Blueprint, request, jsonify, current_app
from ..models import db, Followup, User
from datetime import datetime, timedelta
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.auth_helpers import get_authorized_user

bp = Blueprint("followup", __name__, url_prefix="/api")

@bp.route("/followup/create", methods=["POST"])
@jwt_required()
def create_followup():
    try:
        data = request.get_json()
        
        # Verify Auth & Expiry
        user, err_resp = get_authorized_user()
        if err_resp:
            return err_resp
            
        # Validate required fields
        required_fields = ["reminder_id", "user_id", "phone", "date_time"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Parse date_time
        # Parse date_time
        try:
            # Handle potential ISO format differences
            dt_str = data["date_time"].replace('Z', '+00:00')
            date_time = datetime.fromisoformat(dt_str)
            # Strip timezone info to store as local time (naive datetime)
            # This preserves the time value without UTC conversion
            if date_time.tzinfo is not None:
                date_time = date_time.replace(tzinfo=None)
        except ValueError:
            return jsonify({"error": "Invalid date_time format"}), 400

        # Parse created_at if provided, else now
        created_at = datetime.utcnow()
        if "created_at" in data:
            try:
                cat_str = data["created_at"].replace('Z', '+00:00')
                created_at = datetime.fromisoformat(cat_str)
                # Strip timezone info to store as local time
                if created_at.tzinfo is not None:
                    created_at = created_at.replace(tzinfo=None)
            except ValueError:
                pass # Fallback to now

        followup = Followup(
            id=data["reminder_id"],
            user_id=user.id, # Enforce current user ownership
            contact_name=data.get("contact_name"),
            phone=data["phone"],
            message=data.get("message"),
            date_time=date_time,
            created_at=created_at,
            status="pending"
        )


        db.session.add(followup)
        
        # Auto-status update logic removed per user request.
        
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Reminder saved",
            "reminder_id": followup.id
        }), 201

    except Exception as e:
        current_app.logger.exception("Create followup failed")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route("/admin/followups", methods=["GET"])
@jwt_required()
def get_admin_followups():
    try:
        claims = get_jwt()
        if claims.get("role") != "admin":
            return jsonify({"error": "Admin access only"}), 403

        admin_id = int(get_jwt_identity())

        user_id = request.args.get("user_id")
        date_filter = request.args.get("filter") # today, tomorrow, yesterday, all

        # Join Followup with User to get User Name (Outer join to show records even if user missing)
        query = db.session.query(Followup, User.name).outerjoin(User, Followup.user_id == User.id)

        # Apply User Filter
        if user_id and user_id.lower() != "all":
            query = query.filter(Followup.user_id == user_id)

        # Apply Date Filter
        if date_filter and date_filter.lower() != "all":
            # database stores naive Local Time (aligned with System Time)
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            if date_filter == "today":
                # Filter for today
                query = query.filter(Followup.date_time >= today_start, 
                                     Followup.date_time < today_start + timedelta(days=1))
            
            elif date_filter == "tomorrow":
                 # Filter for tomorrow
                tomorrow_start = today_start + timedelta(days=1)
                query = query.filter(Followup.date_time >= tomorrow_start, 
                                     Followup.date_time < tomorrow_start + timedelta(days=1))
            
            elif date_filter == "yesterday":
                # Filter for yesterday
                yesterday_start = today_start - timedelta(days=1)
                query = query.filter(Followup.date_time >= yesterday_start, 
                                     Followup.date_time < today_start)

        # Fetch and sort
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 30, type=int)
        
        # Order by created_at desc (ambiguous column name 'created_at' needs specification)
        # Followup.created_at
        pagination = query.order_by(Followup.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        
        followups = []
        for f, user_name in pagination.items:
            f_dict = f.to_dict()
            f_dict["user_name"] = user_name # Inject User Name
            followups.append(f_dict)
        
        meta = {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev
        }
        
        return jsonify({"followups": followups, "meta": meta}), 200
        
    except Exception as e:
        current_app.logger.exception("Fetch followups failed")
        return jsonify({"error": str(e)}), 500
