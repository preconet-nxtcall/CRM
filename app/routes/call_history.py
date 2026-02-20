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
import os
import boto3

def get_presigned_url(object_key, expires_in=3600):
    if not object_key or object_key.startswith("uploads/"):
        return None
    
    wasabi_access_key = os.getenv("WASABI_ACCESS_KEY_ID") or os.getenv("WASABI_ACCESS_KEY")
    wasabi_secret_key = os.getenv("WASABI_SECRET_ACCESS_KEY") or os.getenv("WASABI_SECRET_KEY")
    wasabi_bucket = os.getenv("WASABI_BUCKET_NAME")
    wasabi_region = os.getenv("WASABI_REGION", "us-east-1")
    
    if not all([wasabi_access_key, wasabi_secret_key, wasabi_bucket]):
        return None

    wasabi_endpoint = os.getenv("WASABI_ENDPOINT_URL", f"https://s3.{wasabi_region}.wasabisys.com")

    s3_client = boto3.client(
        "s3",
        endpoint_url=wasabi_endpoint,
        aws_access_key_id=wasabi_access_key,
        aws_secret_access_key=wasabi_secret_key,
        region_name=wasabi_region
    )
    
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': wasabi_bucket, 'Key': object_key},
            ExpiresIn=expires_in
        )
        return url
    except Exception:
        return None

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
                # 🤖 AUTO-STATUS UPDATE LOGIC REMOVED
                # -----------------------------------------------------
                # Per user request, calls sync but do NOT change lead status.

                
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

        history_data = []
        for r in items:
            record_dict = r.to_dict()
            record_dict["playback_url"] = get_presigned_url(r.recording_path)
            history_data.append(record_dict)

        return jsonify({
            "user_id": user_id,
            "call_history": history_data,
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

        history_data = []
        for r in items:
            record_dict = r.to_dict()
            record_dict["playback_url"] = get_presigned_url(r.recording_path)
            history_data.append(record_dict)

        return jsonify({
            "user_id": user_id,
            "call_history": history_data,
            "meta": meta
        })

    except Exception as e:
        current_app.logger.exception("ADMIN CALL HISTORY ERROR")
        return jsonify({"error": str(e)}), 400


# -------------------------------------------------
# 4️⃣ UPLOAD CALL RECORDING (WASABI)
# -------------------------------------------------
import os
import boto3
from botocore.exceptions import ClientError, BotoCoreError
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
        record = CallHistory.query.filter(
            CallHistory.user_id == user_id,
            CallHistory.phone_number == phone_number,
            CallHistory.timestamp == dt
        ).first()

        if not record:
            # Create new record if one doesn't exist
            record = CallHistory(
                user_id=user_id,
                phone_number=phone_number,
                formatted_number="",
                call_type=call_type.lower() if call_type else "unknown",
                duration=duration,
                timestamp=dt,
                contact_name=contact_name
            )
            db.session.add(record)
            db.session.flush() # Get ID, but don't commit yet

        # ☁️ Upload File to Wasabi (S3)
        wasabi_access_key = os.getenv("WASABI_ACCESS_KEY_ID") or os.getenv("WASABI_ACCESS_KEY")
        wasabi_secret_key = os.getenv("WASABI_SECRET_ACCESS_KEY") or os.getenv("WASABI_SECRET_KEY")
        wasabi_bucket = os.getenv("WASABI_BUCKET_NAME")
        wasabi_region = os.getenv("WASABI_REGION", "us-east-1")
        
        if not all([wasabi_access_key, wasabi_secret_key, wasabi_bucket]):
            db.session.rollback()
            return jsonify({"error": "Storage configuration is missing on the server"}), 500

        wasabi_endpoint = os.getenv("WASABI_ENDPOINT_URL", f"https://s3.{wasabi_region}.wasabisys.com")

        s3_client = boto3.client(
            "s3",
            endpoint_url=wasabi_endpoint,
            aws_access_key_id=wasabi_access_key,
            aws_secret_access_key=wasabi_secret_key,
            region_name=wasabi_region
        )

        original_filename = secure_filename(f"{dt.strftime('%Y%m%d_%H%M%S')}_{phone_number}_{file.filename}")
        object_key = f"recordings/user_{user_id}/{original_filename}"

        try:
            # Ensure file pointer is at the beginning
            file.seek(0)
            s3_client.upload_fileobj(
                file,
                wasabi_bucket,
                object_key,
                ExtraArgs={
                    "ContentType": file.content_type
                }
            )
        except (BotoCoreError, ClientError) as upload_err:
            db.session.rollback()
            current_app.logger.error(f"Wasabi upload failed: {str(upload_err)}")
            return jsonify({"error": "Failed to upload recording to storage"}), 500

        # Store the object key in the DB. This key can later be used to generate a presigned URL.
        record.recording_path = object_key
        
        # Now that upload is successful, we commit the transaction
        db.session.commit()

        # 🔗 Optional Example: How to generate a presigned URL for playback
        # You can use this logic in a separate endpoint to serve the recording securely to the frontend.
        # presigned_url = s3_client.generate_presigned_url(
        #     'get_object',
        #     Params={'Bucket': wasabi_bucket, 'Key': object_key},
        #     ExpiresIn=3600  # URL valid for 1 hour
        # )

        return jsonify({
            "message": "Recording uploaded successfully to storage",
            "id": record.id,
            "path": object_key
            # "playback_url": presigned_url
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("UPLOAD RECORDING ERROR")
        return jsonify({"error": "Upload failed", "detail": str(e)}), 500
