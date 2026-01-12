# app/routes/call_history.py

from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.models import db, User, CallHistory, UserRole, Lead
from app.auth_helpers import get_authorized_user
from sqlalchemy import func

bp = Blueprint("call_history", __name__, url_prefix="/api/call-history")

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 200


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def parse_timestamp(ts_value):
    """Convert timestamp input from ISO string, seconds, or milliseconds."""
    if ts_value is None:
        return None

    # Epoch seconds/milliseconds
    if isinstance(ts_value, (int, float)):
        try:
            # milliseconds
            if ts_value > 1e10:
                return datetime.utcfromtimestamp(ts_value / 1000)
            # seconds
            return datetime.utcfromtimestamp(ts_value)
        except:
            return None

    # ISO string
    if isinstance(ts_value, str):
        try:
            if ts_value.endswith("Z"):
                ts_value = ts_value[:-1] + "+00:00"

            dt = datetime.fromisoformat(ts_value)

            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

            return dt
        except:
            return None

    return None


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if get_jwt().get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


def paginate(query):
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", DEFAULT_PER_PAGE, type=int), MAX_PER_PAGE)

    pag = query.paginate(page=page, per_page=per_page, error_out=False)

    return pag.items, {
        "page": pag.page,
        "per_page": pag.per_page,
        "total": pag.total,
        "pages": pag.pages,
        "has_next": pag.has_next,
        "has_prev": pag.has_prev
    }


# -------------------------------------------------
# 1️⃣ OPTIMIZED SYNC (Mobile → Server)
# -------------------------------------------------
@bp.route("/sync", methods=["POST"])
@jwt_required()
def sync_call_history():
    try:
        user, err_resp = get_authorized_user()
        if err_resp:
            return err_resp
        user_id = user.id

        payload = request.get_json(silent=True) or {}
        call_list = payload.get("call_history", [])

        if not isinstance(call_list, list):
            return jsonify({"error": "'call_history' must be a list"}), 400

        # Load existing records (hash of key fields) to avoid duplicates
        # Key: (timestamp_iso, phone_number, call_type, duration)
        existing_hashes = set()
        existing_query = db.session.query(
            CallHistory.timestamp,
            CallHistory.phone_number,
            CallHistory.call_type,
            CallHistory.duration
        ).filter(CallHistory.user_id == user_id).all()

        for r in existing_query:
            # Normalize timestamp to ISO string (no microseconds) for comparison
            ts_str = r.timestamp.replace(microsecond=0).isoformat() if r.timestamp else ""
            key = f"{ts_str}|{r.phone_number}|{r.call_type}|{r.duration}"
            existing_hashes.add(key)

        saved = 0
        errors = []

        for entry in call_list:
            try:
                phone_number = entry.get("phone_number")
                call_type = entry.get("call_type")
                duration = int(entry.get("duration", 0))
                timestamp_raw = entry.get("timestamp")

                if not phone_number or not timestamp_raw:
                    errors.append({"entry": entry, "error": "Missing fields"})
                    continue

                # Convert and normalize timestamp
                dt = parse_timestamp(timestamp_raw)
                if not dt:
                    errors.append({"entry": entry, "error": "Invalid timestamp"})
                    continue

                # Ensure UTC and strip microseconds
                if dt.tzinfo:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                dt = dt.replace(microsecond=0)

                # Generate key for duplicate check
                ts_str = dt.isoformat()
                key = f"{ts_str}|{phone_number}|{call_type}|{duration}"

                if key in existing_hashes:
                    continue

                new_record = CallHistory(
                    user_id=user_id,
                    phone_number=phone_number,
                    formatted_number=entry.get("formatted_number") or "",
                    call_type=call_type.lower() if call_type else "unknown",
                    duration=duration,
                    timestamp=dt,
                    contact_name=entry.get("contact_name") or ""
                )

                db.session.add(new_record)
                existing_hashes.add(key) 
                saved += 1
                
                # -----------------------------------------------------
                # 🤖 AUTO-CONTACTED LOGIC
                # -----------------------------------------------------
                # If valid call (duration > 15s), mark matching Lead as "contacted"
                if duration > 15:
                    try:
                        # Find a NEW lead with this phone number
                        # (We only touch 'new' leads to avoid overwriting 'converted' or custom statuses)
                        matched_lead = Lead.query.filter_by(phone=phone_number, status="new").first()
                        if matched_lead:
                            matched_lead.status = "contacted"
                            # No need to commit here, it happens at end of sync
                            db.session.add(matched_lead)
                            current_app.logger.info(f"⚡ AUTO-UPDATE: Lead {matched_lead.id} marked as 'contacted' (Call Duration: {duration}s > 15s)")
                    except Exception as lead_err:
                        current_app.logger.error(f"Auto-contact update failed: {lead_err}")
                
            except Exception as e:
                errors.append({"entry": entry, "error": str(e)})
                continue

        # Update user last sync
        user.last_sync = datetime.utcnow()
        db.session.add(user)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "DB commit failed", "detail": str(e)}), 500

        # =========================================================
        # 📊 AUTO-CALCULATE ANALYTICS
        # =========================================================
        try:
            # ---- Total Calls ----
            total_calls = CallHistory.query.filter_by(user_id=user_id).count()

            # ---- Call Type Summary ----
            call_types = (
                db.session.query(
                    CallHistory.call_type,
                    func.count(CallHistory.id)
                )
                .filter(CallHistory.user_id == user_id)
                .group_by(CallHistory.call_type)
                .all()
            )
            # Normalize keys to lowercase for consistency
            call_type_summary = {ctype.lower(): count for ctype, count in call_types}

            # ---- Total Call Duration ----
            total_duration = (
                db.session.query(func.coalesce(func.sum(CallHistory.duration), 0))
                .filter(CallHistory.user_id == user_id)
                .scalar()
                or 0
            )

            # ---- Recent Calls (Optional context) ----
            # We can return the last few calls if needed, or just the summary
            
        except Exception as analytics_error:
            # If analytics fail, we still return success for the sync but log the error
            current_app.logger.error(f"Analytics calc failed: {analytics_error}")
            total_calls = 0
            call_type_summary = {}
            total_duration = 0

        return jsonify({
            "message": "Call history synced successfully",
            "records_saved": saved,
            "errors": errors,
            "analytics": {
                "total_calls": total_calls,
                "call_types": call_type_summary,
                "total_duration_seconds": int(total_duration),
                "last_sync": user.last_sync.isoformat()
            }
        }), 200

    except Exception as e:
        current_app.logger.exception("CALL HISTORY SYNC ERROR")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 400


# -------------------------------------------------
# 2️⃣ USER CALL HISTORY
# -------------------------------------------------
@bp.route("/my", methods=["GET"])
@jwt_required()
def my_call_history():
    try:
        user, err_resp = get_authorized_user()
        if err_resp:
            return err_resp
        user_id = user.id

        q = CallHistory.query.filter_by(user_id=user_id).order_by(CallHistory.timestamp.desc())
        items, meta = paginate(q)

        return jsonify({
            "user_id": user_id,
            "call_history": [r.to_dict() for r in items],
            "meta": meta
        })

    except Exception as e:
        current_app.logger.exception("MY CALL HISTORY ERROR")
        return jsonify({"error": str(e)}), 400


# -------------------------------------------------
# 3️⃣ ADMIN — SPECIFIC USER CALL HISTORY
# -------------------------------------------------
@bp.route("/admin/<int:user_id>", methods=["GET"])
@jwt_required()
@admin_required
def admin_user_call_history(user_id):
    try:
        q = CallHistory.query.filter_by(user_id=user_id).order_by(CallHistory.timestamp.desc())
        items, meta = paginate(q)

        return jsonify({
            "user_id": user_id,
            "call_history": [r.to_dict() for r in items],
            "meta": meta
        })

    except Exception as e:
        current_app.logger.exception("ADMIN CALL HISTORY ERROR")
        return jsonify({"error": str(e)}), 400


# -------------------------------------------------
# 4️⃣ UPLOAD CALL RECORDING
# -------------------------------------------------
import os
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'mp3', 'wav', 'aac', 'm4a', 'amr', 'opus', 'ogg', '3gp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route("/upload-recording", methods=["POST"])
@jwt_required()
def upload_recording():
    try:
        user, err_resp = get_authorized_user()
        if err_resp:
            return err_resp
        user_id = user.id

        # Check if file is present
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "File type not allowed"}), 400

        # Metadata to match record
        phone_number = request.form.get("phone_number")
        timestamp_raw = request.form.get("timestamp")
        call_type = request.form.get("call_type")
        duration = request.form.get("duration", type=int) or 0
        contact_name = request.form.get("contact_name") or ""
        
        if not phone_number or not timestamp_raw:
            return jsonify({"error": "Missing metadata (phone_number, timestamp)"}), 400

        # Parse timestamp
        dt = parse_timestamp(timestamp_raw)
        if not dt:
             return jsonify({"error": "Invalid timestamp"}), 400
        
        # Ensure UTC and strip microseconds for matching
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        dt = dt.replace(microsecond=0)

        # 🔍 Try to find existing record
        # We match broadly on timestamp (within seconds tolerance?) 
        # For now, exact match on normalized timestamp as per sync logic
        record = CallHistory.query.filter(
            CallHistory.user_id == user_id,
            CallHistory.phone_number == phone_number,
            CallHistory.timestamp == dt
        ).first()

        # If not found exactly, maybe allow small drift? (Optional, skipping for now)

        if not record:
            # Create new record if one doesn't exist (Recording arrived before sync or missed sync)
            record = CallHistory(
                user_id=user_id,
                phone_number=phone_number,
                formatted_number="", # Can be added if sent
                call_type=call_type.lower() if call_type else "unknown",
                duration=duration,
                timestamp=dt,
                contact_name=contact_name
            )
            db.session.add(record)
            db.session.flush() # Get ID
        
        # 📂 Save File
        # Structure: uploads/recordings/user_{id}/filename
        # Fix V2.6: Use explicit os.getcwd() to ensure we save to backend/uploads (which is verified to exist/be compatible)
        # rather than app.root_path/static which might be missing.
        upload_folder = os.path.join(os.getcwd(), 'uploads', 'recordings', f'user_{user_id}')
        os.makedirs(upload_folder, exist_ok=True)
        
        original_filename = secure_filename(f"{dt.strftime('%Y%m%d_%H%M%S')}_{phone_number}_{file.filename}")
        original_file_path = os.path.join(upload_folder, original_filename)
        file.save(original_file_path)
        
        final_filename = original_filename
        final_file_path = original_file_path
        
        # 🎵 AUTO-CONVERT TO MP3 (if .amr or .3gp)
        # Browsers don't support AMR/3GP. We use pydub/ffmpeg to convert.
        lower_name = original_filename.lower()
        if lower_name.endswith('.amr') or lower_name.endswith('.3gp'):
            try:
                from pydub import AudioSegment
                
                # Input format
                fmt = 'amr' if lower_name.endswith('.amr') else '3gp'
                
                print(f"🔄 Converting {fmt.upper()} to MP3: {original_filename}")
                
                # Load audio
                audio = AudioSegment.from_file(original_file_path, format=fmt)
                
                # Define new filename
                mp3_filename = os.path.splitext(original_filename)[0] + ".mp3"
                mp3_path = os.path.join(upload_folder, mp3_filename)
                
                # Export as mp3
                audio.export(mp3_path, format="mp3")
                
                print(f"✅ Conversion successful: {mp3_filename}")
                
                # Update references (We serve the MP3)
                final_filename = mp3_filename
                final_file_path = mp3_path
                
                # Cleanup original? (Optional: Keep for backup or delete to save space)
                # os.remove(original_file_path) 
                
            except Exception as conv_err:
                print(f"❌ Audio conversion failed: {conv_err}")
                print("⚠️ Falling back to original file (Download required for playback)")
                # If conversion fails (e.g. ffmpeg not installed), we keep original
                pass

        # Store relative path for frontend access
        # Assuming typical static setup: /static/uploads/...
        relative_path = f"uploads/recordings/user_{user_id}/{final_filename}"
        record.recording_path = relative_path
        
        db.session.commit()

        return jsonify({
            "message": "Recording uploaded successfully",
            "id": record.id,
            "path": relative_path
        }), 200

    except Exception as e:
        current_app.logger.exception("UPLOAD RECORDING ERROR")
        return jsonify({"error": "Upload failed", "detail": str(e)}), 500
