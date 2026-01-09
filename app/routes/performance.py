from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import db
from ..models import User

performance_bp = Blueprint("admin_performance", __name__, url_prefix="/api/admin")


# ----------------------------
# Admin access check helper
# ----------------------------
def admin_required():
    claims = get_jwt()
    return claims.get("role") == "admin"

# ==========================================================
#  🔥 ADMIN — PERFORMANCE ANALYTICS
# ==========================================================
@performance_bp.route("/performance", methods=["GET"])
@jwt_required()
def admin_performance():

    if not admin_required():
        return jsonify({"error": "Admin only"}), 403

    admin_id = int(get_jwt_identity())

    # sorting support (optional)
    sort = request.args.get("sort", "desc")

    query = User.query.filter_by(admin_id=admin_id)

    if sort == "asc":
        query = query.order_by(User.performance_score.asc())
    else:
        query = query.order_by(User.performance_score.desc())

    users = query.limit(50).all()

    labels = [u.name for u in users]
    values = [round((u.performance_score or 0), 2) for u in users]
    ids = [u.id for u in users]

    return jsonify({
        "labels": labels,
        "values": values,
        "user_ids": ids,
        "count": len(users)
    }), 200




