# app/routes/db_repair.py

from flask import Blueprint, jsonify
from sqlalchemy import text
from app.models import db

bp = Blueprint("db_repair", __name__, url_prefix="/api/repair")


@bp.route("/fix-db", methods=["POST"])
def repair_database():
    try:
        # Reset failed transaction
        db.session.rollback()

        # ------------ FIX ATTENDANCE COLUMN ------------
        try:
            db.session.execute(text("""
                ALTER TABLE attendances
                ADD COLUMN IF NOT EXISTS external_id VARCHAR(64);
            """))
            db.session.commit()
        except Exception as e:
            return jsonify({"error": "Attendance fix failed", "detail": str(e)}), 500

        # ------------ FIX CALL HISTORY TABLE ------------
        # Drop broken table completely
        try:
            db.session.execute(text("DROP TABLE IF EXISTS call_history CASCADE;"))
            db.session.commit()
        except Exception as e:
            return jsonify({"error": "Drop call_history failed", "detail": str(e)}), 500

        # Recreate fresh table
        try:
            db.create_all()
        except Exception as e:
            return jsonify({"error": "Recreate call_history failed", "detail": str(e)}), 500

        return jsonify({"message": "Database repaired successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Repair failed", "detail": str(e)}), 500