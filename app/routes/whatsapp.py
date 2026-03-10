# app/routes/whatsapp.py
"""
WhatsApp CRM Messaging — Blueprint
Handles: config, template management, send, inbox, webhook
Brandmo API Base: https://crmpi.brandmo.in/api/meta/v19.0
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
from sqlalchemy import nulls_last
import requests as _ext_requests
from ..models import (
    db, Admin, User,
    WhatsAppConfig, WATemplate, WAContact, WAConversation, WAMessage,
    WAMessageStatusLog, WAConversationLock, WALeadAssignConfig,
)

bp = Blueprint("whatsapp", __name__, url_prefix="/api/whatsapp")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def admin_required():
    return get_jwt().get("role") == "admin"

def get_admin_or_err():
    """Return (admin, None) or (None, error_response)."""
    try:
        admin_id = int(get_jwt_identity())
    except Exception:
        return None, (jsonify({"error": "Invalid token"}), 401)
    admin = Admin.query.get(admin_id)
    if not admin:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if not admin.is_active:
        return None, (jsonify({"error": "Account deactivated"}), 403)
    # SaaS: block expired admins from using WhatsApp features
    if admin.is_expired():
        return None, (jsonify({"error": "Subscription expired. Please renew to use WhatsApp features."}), 403)
    return admin, None

def get_wa_config(admin_id):
    """Return WhatsAppConfig or None."""
    return WhatsAppConfig.query.filter_by(admin_id=admin_id).first()

def get_or_create_contact(admin_id, phone, profile_name=None, lead_id=None):
    """Find or create WAContact for this admin+phone.
    
    Handles concurrent-webhook race conditions via IntegrityError retry.
    """
    from sqlalchemy.exc import IntegrityError
    contact = WAContact.query.filter_by(admin_id=admin_id, phone_number=phone).first()
    if not contact:
        try:
            contact = WAContact(
                admin_id=admin_id,
                phone_number=phone,
                profile_name=profile_name,
                name=profile_name,
                lead_id=lead_id,
            )
            db.session.add(contact)
            db.session.flush()
        except IntegrityError:
            # Concurrent request already inserted — roll back and fetch
            db.session.rollback()
            contact = WAContact.query.filter_by(admin_id=admin_id, phone_number=phone).first()
    elif profile_name and not contact.profile_name:
        contact.profile_name = profile_name
        contact.name = profile_name
    return contact

def get_or_create_conversation(admin_id, contact_id):
    """Find or create WAConversation for admin+contact.
    
    Handles concurrent-webhook race conditions via IntegrityError retry.
    """
    from sqlalchemy.exc import IntegrityError
    conv = WAConversation.query.filter_by(admin_id=admin_id, contact_id=contact_id).first()
    if not conv:
        try:
            conv = WAConversation(admin_id=admin_id, contact_id=contact_id, status="open")
            db.session.add(conv)
            db.session.flush()
        except IntegrityError:
            # Concurrent request already created this conversation
            db.session.rollback()
            conv = WAConversation.query.filter_by(admin_id=admin_id, contact_id=contact_id).first()
    return conv


# ─────────────────────────────────────────────
# 1. CONFIG — GET / SAVE
# ─────────────────────────────────────────────

@bp.route("/config", methods=["GET"])
@jwt_required()
def get_config():
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    cfg = get_wa_config(admin.id)
    if not cfg:
        return jsonify({"config": None}), 200
    return jsonify({"config": cfg.to_dict()}), 200


@bp.route("/config", methods=["POST"])
@jwt_required()
def save_config():
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    data = request.get_json() or {}
    access_token    = data.get("access_token", "").strip()
    phone_number_id = data.get("phone_number_id", "").strip()
    waba_id         = data.get("waba_id", "").strip()

    if not access_token or not phone_number_id or not waba_id:
        return jsonify({"error": "access_token, phone_number_id and waba_id are required"}), 400

    cfg = get_wa_config(admin.id)
    if not cfg:
        cfg = WhatsAppConfig(admin_id=admin.id)
        db.session.add(cfg)

    cfg.set_token(access_token)
    cfg.phone_number_id = phone_number_id
    cfg.waba_id         = waba_id
    cfg.is_active       = True

    # Optional fields
    if data.get("business_name"):
        cfg.business_name = data["business_name"]
    if data.get("phone_display"):
        cfg.phone_display = data["phone_display"]
    if data.get("verify_token"):
        cfg.verify_token = data["verify_token"]

    db.session.commit()
    return jsonify({"message": "WhatsApp config saved", "config": cfg.to_dict()}), 200


@bp.route("/config", methods=["DELETE"])
@jwt_required()
def disconnect_config():
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    cfg = get_wa_config(admin.id)
    if cfg:
        cfg.is_active = False
        db.session.commit()
    return jsonify({"message": "WhatsApp disconnected"}), 200


# ─────────────────────────────────────────────
# 2. TEMPLATES — LIST
# ─────────────────────────────────────────────

@bp.route("/templates", methods=["GET"])
@jwt_required()
def list_templates():
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    status_filter = request.args.get("status")  # APPROVED / PENDING / REJECTED
    q = WATemplate.query.filter_by(admin_id=admin.id)
    if status_filter:
        q = q.filter_by(status=status_filter.upper())
    q = q.order_by(WATemplate.synced_at.desc())

    templates = [t.to_dict() for t in q.all()]
    return jsonify({"templates": templates, "count": len(templates)}), 200


# ─────────────────────────────────────────────
# 3. TEMPLATES — SYNC FROM BRANDMO
# ─────────────────────────────────────────────

@bp.route("/templates/sync", methods=["POST"])
@jwt_required()
def sync_templates():
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    cfg = get_wa_config(admin.id)
    if not cfg or not cfg.is_active:
        return jsonify({"error": "WhatsApp not connected. Please save your config first."}), 400

    try:
        from app.services.whatsapp_service import BrandmoService
        svc = BrandmoService(cfg)
        count = svc.sync_templates()
        return jsonify({"message": f"Synced {count} templates", "synced": count}), 200
    except _ext_requests.HTTPError as e:
        body = ""
        try:
            body = e.response.json().get("error", {}).get("message", e.response.text)
        except Exception:
            body = str(e)
        current_app.logger.error(f"Template sync HTTP error: {body}")
        return jsonify({"error": f"Brandmo API error: {body}"}), 502
    except Exception as e:
        current_app.logger.exception("Template sync failed")
        return jsonify({"error": f"Sync failed: {str(e)}"}), 500


# ─────────────────────────────────────────────
# 4. TEMPLATES — CREATE
# ─────────────────────────────────────────────

@bp.route("/templates/create", methods=["POST"])
@jwt_required()
def create_template():
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    cfg = get_wa_config(admin.id)
    if not cfg or not cfg.is_active:
        return jsonify({"error": "WhatsApp not connected"}), 400

    data = request.get_json() or {}
    name       = (data.get("name") or "").strip().lower().replace(" ", "_")
    category   = (data.get("category") or "UTILITY").upper()
    language   = (data.get("language") or "en").strip()
    header_text = data.get("header_text", "")
    body_text   = data.get("body_text", "")
    footer_text = data.get("footer_text", "")
    buttons     = data.get("buttons", [])

    if not name or not body_text:
        return jsonify({"error": "name and body_text are required"}), 400

    # Build components array
    components = []
    if header_text:
        components.append({
            "type":   "HEADER",
            "format": "TEXT",
            "text":   header_text,
        })

    # Count variables in body
    import re as _re
    var_matches = _re.findall(r"\{\{\d+\}\}", body_text)
    body_component = {"type": "BODY", "text": body_text}
    if var_matches:
        # Build numbered example placeholders (e.g. "Value 1", "Value 2")
        body_component["example"] = {
            "body_text": [[f"Value {i+1}" for i in range(len(var_matches))]]
        }
    components.append(body_component)

    if footer_text:
        components.append({"type": "FOOTER", "text": footer_text})

    if buttons:
        components.append({"type": "BUTTONS", "buttons": buttons})

    try:
        from app.services.whatsapp_service import BrandmoService
        svc = BrandmoService(cfg)
        result = svc.create_template(name, category, language, components)

        # Store locally as pending
        tmpl = WATemplate(
            admin_id=admin.id,
            template_id=result.get("id"),
            name=name,
            language=language,
            category=category,
            status="PENDING",
            components=components,
            body_text=body_text,
            variable_count=len(var_matches),
            synced_at=datetime.utcnow(),
        )
        db.session.add(tmpl)
        db.session.commit()

        return jsonify({"message": "Template submitted for review", "template": tmpl.to_dict()}), 201
    except _ext_requests.HTTPError as e:
        db.session.rollback()
        error_msg = str(e)
        try:
            err_json = e.response.json()
            # Brandmo wraps Meta errors in {"error": {"message": "...", "error_data": {...}}}
            err_obj = err_json.get("error", {})
            error_msg = err_obj.get("message") or err_obj.get("error_user_msg") or e.response.text
            current_app.logger.error(
                f"Template create HTTP {e.response.status_code}: {err_json}"
            )
        except Exception:
            current_app.logger.error(f"Template create error (non-JSON): {e.response.text}")
        return jsonify({"error": f"Brandmo API error: {error_msg}"}), 502
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Template creation failed")
        return jsonify({"error": f"Failed: {str(e)}"}), 500


# ─────────────────────────────────────────────
# 5. TEMPLATES — DELETE
# ─────────────────────────────────────────────

@bp.route("/templates/<int:template_id>", methods=["DELETE"])
@jwt_required()
def delete_template(template_id):
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    tmpl = WATemplate.query.filter_by(id=template_id, admin_id=admin.id).first()
    if not tmpl:
        return jsonify({"error": "Template not found"}), 404

    cfg = get_wa_config(admin.id)
    if cfg and cfg.is_active:
        try:
            from app.services.whatsapp_service import BrandmoService
            svc = BrandmoService(cfg)
            svc.delete_template(tmpl.name)
        except Exception as e:
            current_app.logger.warning(f"API delete failed (deleting locally anyway): {e}")

    db.session.delete(tmpl)
    db.session.commit()
    return jsonify({"message": "Template deleted"}), 200


# ─────────────────────────────────────────────
# 6. SEND TEMPLATE MESSAGE
# ─────────────────────────────────────────────

@bp.route("/send-template", methods=["POST"])
@jwt_required()
def send_template():
    """
    Body: { phone, template_name, parameters: [...], language?: "en" }
    Looks up template from DB, sends via Brandmo, stores message record.
    """
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    cfg = get_wa_config(admin.id)
    if not cfg or not cfg.is_active:
        return jsonify({"error": "WhatsApp not connected"}), 400

    data          = request.get_json() or {}
    phone         = (data.get("phone") or "").strip()
    template_name = (data.get("template_name") or "").strip()
    parameters    = data.get("parameters", [])
    language      = data.get("language", "en")

    if not phone or not template_name:
        return jsonify({"error": "phone and template_name are required"}), 400

    # Validate template exists and is approved
    tmpl = WATemplate.query.filter_by(
        admin_id=admin.id,
        name=template_name,
    ).first()
    if not tmpl:
        return jsonify({"error": f"Template '{template_name}' not found. Please sync templates first."}), 404
    if tmpl.status.upper() != "APPROVED":
        return jsonify({"error": f"Template status is '{tmpl.status}'. Only APPROVED templates can be sent."}), 400

    try:
        from app.services.whatsapp_service import BrandmoService
        svc    = BrandmoService(cfg)
        result = svc.send_template(phone, template_name, tmpl.language or language, parameters)

        # Extract wamid from Brandmo response
        wamid = None
        messages_list = result.get("messages", [])
        if messages_list:
            wamid = messages_list[0].get("id")

        # Store contact + conversation + message
        contact = get_or_create_contact(admin.id, phone)
        conv    = get_or_create_conversation(admin.id, contact.id)

        # Build text preview of template
        body_preview = tmpl.body_text or template_name
        for i, val in enumerate(parameters, start=1):
            body_preview = body_preview.replace(f"{{{{{i}}}}}", val)

        # Only save WAMessage when Brandmo confirmed a real message ID
        if wamid:
            msg = WAMessage(
                conversation_id = conv.id,
                admin_id        = admin.id,
                whatsapp_msg_id = wamid,
                sender_type     = "agent",
                sender_id       = admin.id,
                message_type    = "template",
                message_text    = body_preview,
                template_name   = template_name,
                status          = "sent",
            )
            db.session.add(msg)
        conv.last_message_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            "message":    "Template sent",
            "wamid":      wamid,
            "message_id": msg.id if wamid else None,
            "raw":        result,
        }), 200

    except _ext_requests.HTTPError as e:
        db.session.rollback()
        body = ""
        try:
            body = e.response.json().get("error", {}).get("message", e.response.text)
        except Exception:
            body = str(e)
        current_app.logger.error(f"Send template HTTP error: {body}")
        return jsonify({"error": f"Brandmo API error: {body}"}), 502
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Send template failed")
        return jsonify({"error": f"Failed to send: {str(e)}"}), 500


# ─────────────────────────────────────────────
# 7. CONVERSATIONS — INBOX LIST
# ─────────────────────────────────────────────

@bp.route("/conversations", methods=["GET"])
@jwt_required()
def list_conversations():
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    status = request.args.get("status", "open")
    q = WAConversation.query.filter_by(admin_id=admin.id)
    if status != "all":
        q = q.filter_by(status=status)
    q = q.order_by(nulls_last(WAConversation.last_message_at.desc()))

    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(int(request.args.get("per_page", 30)), 100)
    pag      = q.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for conv in pag.items:
        d = conv.to_dict(include_last_message=True)
        items.append(d)

    return jsonify({
        "conversations": items,
        "meta": {
            "page":     pag.page,
            "per_page": pag.per_page,
            "total":    pag.total,
            "pages":    pag.pages,
        },
    }), 200


# ─────────────────────────────────────────────
# 8. MESSAGES — FOR A CONVERSATION
# ─────────────────────────────────────────────

@bp.route("/conversations/<int:conv_id>/messages", methods=["GET"])
@jwt_required()
def list_messages(conv_id):
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    conv = WAConversation.query.filter_by(id=conv_id, admin_id=admin.id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(int(request.args.get("per_page", 50)), 200)

    q = (
        WAMessage.query
        .filter_by(conversation_id=conv_id)
        .order_by(WAMessage.created_at.asc())
    )
    pag      = q.paginate(page=page, per_page=per_page, error_out=False)
    messages = [m.to_dict() for m in pag.items]

    # Mark as read AFTER fetching so unread is only cleared if query succeeded
    if conv.unread_count > 0:
        conv.unread_count = 0
        db.session.commit()

    return jsonify({
        "conversation": conv.to_dict(),
        "messages":     messages,
        "meta": {
            "page":     pag.page,
            "per_page": pag.per_page,
            "total":    pag.total,
            "pages":    pag.pages,
        },
    }), 200


# ─────────────────────────────────────────────
# 9. SEND TEXT / TEMPLATE IN CONVERSATION
# ─────────────────────────────────────────────

@bp.route("/conversations/<int:conv_id>/send", methods=["POST"])
@jwt_required()
def send_in_conversation(conv_id):
    """
    Body: { type: "text"|"template", text?: str, template_name?: str, parameters?: list }
    Enforces 24h window rule: only template allowed if window expired.
    """
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    conv = WAConversation.query.filter_by(id=conv_id, admin_id=admin.id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    cfg = get_wa_config(admin.id)
    if not cfg or not cfg.is_active:
        return jsonify({"error": "WhatsApp not connected"}), 400

    data      = request.get_json() or {}
    msg_type  = data.get("type", "text")
    phone     = conv.contact.phone_number if conv.contact else None

    if not phone:
        return jsonify({"error": "No phone number for contact"}), 400

    # 24-hour window check
    within_window = conv.is_within_24h_window()
    if msg_type == "text" and not within_window:
        return jsonify({
            "error": "24-hour conversation window has expired. You must send a template message to re-open the conversation.",
            "within_window": False,
        }), 400

    # Enforce conversation lock expiry before allowing send
    if conv.lock and not conv.lock.is_expired():
        from flask_jwt_extended import get_jwt_identity as _get_id
        current_actor_id = int(_get_id())
        if conv.lock.agent_id != current_actor_id:
            return jsonify({
                "error": "Conversation is locked by another agent.",
                "locked_by": conv.lock.agent_id,
            }), 409

    try:
        from app.services.whatsapp_service import BrandmoService
        svc    = BrandmoService(cfg)
        wamid  = None
        body_preview = ""

        if msg_type == "text":
            text   = (data.get("text") or "").strip()
            if not text:
                return jsonify({"error": "text is required"}), 400
            result = svc.send_text(phone, text)
            messages_list = result.get("messages", [])
            if messages_list:
                wamid = messages_list[0].get("id")
            body_preview = text

        elif msg_type == "template":
            template_name = (data.get("template_name") or "").strip()
            parameters    = data.get("parameters", [])
            if not template_name:
                return jsonify({"error": "template_name is required"}), 400

            tmpl = WATemplate.query.filter_by(admin_id=admin.id, name=template_name).first()
            if not tmpl:
                return jsonify({"error": "Template not found"}), 404
            # Enforce approval status (case-insensitive)
            if tmpl.status.upper() != "APPROVED":
                return jsonify({"error": f"Template '{template_name}' is not APPROVED (status: {tmpl.status}). Cannot send."}), 400

            language = tmpl.language or "en"
            result   = svc.send_template(phone, template_name, language, parameters)
            messages_list = result.get("messages", [])
            if messages_list:
                wamid = messages_list[0].get("id")

            body_preview = tmpl.body_text or template_name
            for i, val in enumerate(parameters, start=1):
                body_preview = body_preview.replace(f"{{{{{i}}}}}", val)
        else:
            return jsonify({"error": f"Unsupported message type: {msg_type}"}), 400

        # Only save WAMessage when Brandmo confirmed a real message ID
        if wamid:
            msg = WAMessage(
                conversation_id = conv_id,
                admin_id        = admin.id,
                whatsapp_msg_id = wamid,
                sender_type     = "agent",
                sender_id       = admin.id,
                message_type    = msg_type,
                message_text    = body_preview,
                template_name   = data.get("template_name") if msg_type == "template" else None,
                status          = "sent",
            )
            db.session.add(msg)
        conv.last_message_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            "message":    "Sent",
            "wamid":      wamid,
            "message_id": msg.id if wamid else None,
        }), 200

    except _ext_requests.HTTPError as e:
        db.session.rollback()
        body = ""
        try:
            body = e.response.json().get("error", {}).get("message", e.response.text)
        except Exception:
            body = str(e)
        current_app.logger.error(f"Send message HTTP error: {body}")
        return jsonify({"error": f"Brandmo API error: {body}"}), 502
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Send in conversation failed")
        return jsonify({"error": f"Failed to send: {str(e)}"}), 500


# ─────────────────────────────────────────────
# 10. 24-HOUR WINDOW CHECK
# ─────────────────────────────────────────────

@bp.route("/conversations/<int:conv_id>/window", methods=["GET"])
@jwt_required()
def check_window(conv_id):
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    conv = WAConversation.query.filter_by(id=conv_id, admin_id=admin.id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    within = conv.is_within_24h_window()
    last_at = conv.last_customer_msg_at

    expires_at = None
    if last_at:
        expires_at = (last_at + timedelta(hours=24)).isoformat()

    return jsonify({
        "within_window": within,
        "last_customer_msg_at": last_at.isoformat() if last_at else None,
        "window_expires_at":    expires_at,
        "can_send_text":        within,
    }), 200


# ─────────────────────────────────────────────
# 11. WEBHOOK — VERIFY (GET) + RECEIVE (POST)
# ─────────────────────────────────────────────

@bp.route("/webhook", methods=["GET"])
def webhook_verify():
    """
    Webhook verification endpoint — handles two formats:

    1. Brandmo format: ?echo=true&challange=<VALUE>
       → must echo back exactly <VALUE> as plain text body

    2. Meta-standard: ?hub.mode=subscribe&hub.verify_token=<TOKEN>&hub.challenge=<CHALLENGE>
       → validate token, echo back the challenge
    """
    # ── Case 1: Brandmo echo verification ──
    echo      = request.args.get("echo")
    challange = request.args.get("challange")   # Brandmo typo: "challange" not "challenge"

    if echo == "true" and challange:
        current_app.logger.info(f"[Webhook] Brandmo echo verification — echoing: {challange}")
        return challange, 200, {"Content-Type": "text/plain"}

    # ── Case 2: Meta-standard subscribe handshake ──
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    global_token = current_app.config.get("WA_WEBHOOK_VERIFY_TOKEN", "nxtcall_wa_webhook_2026")

    if mode == "subscribe":
        if token == global_token:
            current_app.logger.info("[Webhook] Meta subscription verified (global token)")
            return challenge or "", 200

        cfg = WhatsAppConfig.query.filter_by(verify_token=token).first()
        if cfg:
            current_app.logger.info(f"[Webhook] Meta subscription verified (admin {cfg.admin_id})")
            return challenge or "", 200

    # ── Case 3: Plain GET with no params — just return 200 ──
    if not mode and not echo:
        current_app.logger.info("[Webhook] Plain GET ping — returning 200 OK")
        return "OK", 200

    current_app.logger.warning(f"[Webhook] Verification failed — mode={mode} echo={echo}")
    return "Forbidden", 403


@bp.route("/webhook", methods=["POST"])
def webhook_receive():
    """
    Receive and process WhatsApp events from Brandmo/Meta.
    Handles: incoming messages, status updates (sent/delivered/read/failed).
    Routes events to the right admin by phone_number_id.
    """
    data = request.get_json(silent=True) or {}

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                val = change.get("value", {})

                # --- Metadata: identify admin by phone_number_id ---
                metadata = val.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")

                cfg = None
                if phone_number_id:
                    cfg = WhatsAppConfig.query.filter_by(
                        phone_number_id=phone_number_id,
                        is_active=True,
                    ).first()

                admin_id = cfg.admin_id if cfg else None

                # --- INCOMING MESSAGES ---
                for msg_obj in val.get("messages", []):
                    _handle_inbound_message(admin_id, msg_obj, val)

                # --- STATUS UPDATES ---
                for status_obj in val.get("statuses", []):
                    _handle_status_update(status_obj)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        current_app.logger.exception("Webhook processing error")
        # Always return 200 to Brandmo — returning 5xx causes automatic retries
        # which would re-process the same events and cause duplicate messages.
        return jsonify({"status": "ok", "warning": "internal processing error"}), 200


def _handle_inbound_message(admin_id, msg_obj, val):
    """Process one incoming message object from the webhook payload."""
    if not admin_id:
        return

    wamid        = msg_obj.get("id")
    from_phone   = msg_obj.get("from")
    timestamp_ts = int(msg_obj.get("timestamp", 0))
    msg_type     = msg_obj.get("type", "text")

    # Deduplicate — scoped to admin_id so cross-admin wamid collision doesn't suppress a valid inbound
    if wamid and WAMessage.query.filter_by(whatsapp_msg_id=wamid, admin_id=admin_id).first():
        return

    # Profile name
    profile_name = None
    contacts_list = val.get("contacts", [])
    if contacts_list:
        profile_name = contacts_list[0].get("profile", {}).get("name")

    # Extract text
    message_text  = None
    media_id      = None
    media_mime    = None
    media_filename = None

    if msg_type == "text":
        message_text = msg_obj.get("text", {}).get("body")
    elif msg_type in ("image", "video", "audio", "document", "sticker"):
        media_info    = msg_obj.get(msg_type, {})
        media_id      = media_info.get("id")
        media_mime    = media_info.get("mime_type")
        media_filename = media_info.get("filename")
        message_text  = media_info.get("caption")
    elif msg_type == "interactive":
        interactive = msg_obj.get("interactive", {})
        itype = interactive.get("type")
        if itype == "button_reply":
            message_text = interactive.get("button_reply", {}).get("title")
        elif itype == "list_reply":
            message_text = interactive.get("list_reply", {}).get("title")
    elif msg_type == "location":
        loc = msg_obj.get("location", {})
        message_text = f"📍 {loc.get('name', 'Location')}: {loc.get('latitude')},{loc.get('longitude')}"

    # Upsert contact & conversation
    contact = get_or_create_contact(admin_id, from_phone, profile_name)
    conv    = get_or_create_conversation(admin_id, contact.id)

    msg_dt = datetime.utcfromtimestamp(timestamp_ts) if timestamp_ts else datetime.utcnow()

    # Update 24h window
    conv.last_customer_msg_at = msg_dt
    conv.last_message_at      = msg_dt
    conv.unread_count         = (conv.unread_count or 0) + 1
    if conv.status == "closed":
        conv.status = "open"

    msg = WAMessage(
        conversation_id = conv.id,
        admin_id        = admin_id,
        whatsapp_msg_id = wamid,
        sender_type     = "customer",
        message_type    = msg_type,
        message_text    = message_text,
        media_id        = media_id,
        media_mime_type = media_mime,
        media_filename  = media_filename,
        status          = "received",
        created_at      = msg_dt,
    )
    db.session.add(msg)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        from flask import current_app as _app
        _app.logger.error(f"[Webhook] Failed to save inbound message {wamid}: {e}")


def _handle_status_update(status_obj):
    """Update WAMessage delivery status from webhook."""
    wamid     = status_obj.get("id")
    status    = status_obj.get("status")  # sent / delivered / read / failed
    timestamp = status_obj.get("timestamp")

    if not wamid or not status:
        return

    msg = WAMessage.query.filter_by(whatsapp_msg_id=wamid).first()
    if not msg:
        return

    # Status precedence: failed > read > delivered > sent
    precedence = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}
    current_p  = precedence.get(msg.status, 0)
    new_p      = precedence.get(status, 0)

    if new_p >= current_p:
        msg.status = status
        if status == "failed":
            error_data    = status_obj.get("errors", [{}])[0]
            msg.error_code    = str(error_data.get("code", ""))
            msg.error_message = error_data.get("message", "")

    # Always log
    log = WAMessageStatusLog(
        message_id  = msg.id,
        status      = status,
        timestamp   = datetime.utcfromtimestamp(int(timestamp)) if timestamp else datetime.utcnow(),
        raw_payload = str(status_obj),
    )
    db.session.add(log)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[Webhook] Failed to save status update for {wamid}: {e}")


# ─────────────────────────────────────────────────────────
# LEAD ASSIGNMENT AUTO-WHATSAPP HELPER
# ─────────────────────────────────────────────────────────

def _resolve_params(param_list, context):
    """
    Replace {{placeholder}} variables in each param string with real values.

    context dict keys:
        lead_name, lead_phone, lead_source, agent_name, agent_phone
    """
    resolved = []
    for p in (param_list or []):
        s = str(p)
        for key, val in context.items():
            s = s.replace("{{" + key + "}}", str(val or ""))
        resolved.append(s)
    return resolved


def normalize_phone(phone: str) -> str:
    """
    Normalize a phone number to E.164 format required by WhatsApp/Brandmo.
    Rules:
      - Strip spaces, dashes, parentheses, + prefix
      - If 10 digits remain (Indian mobile), prepend country code 91
      - If already has country code (11-13 digits), use as-is
      - Returns empty string if input is empty/None
    """
    if not phone:
        return ""
    import re as _re
    # Remove all non-digit characters
    digits = _re.sub(r"\D", "", phone)
    if not digits:
        return ""
    # 10-digit number → assume Indian → prepend 91
    if len(digits) == 10:
        return "91" + digits
    # Already has country code (11-13 digits) → use as-is
    return digits


def send_lead_assignment_whatsapp(admin_id, lead, agent):
    """
    Non-blocking. Call this after a lead is assigned to an agent.

    Sends:
      • agent_template → agent.phone  (notify agent of new lead)
      • lead_template  → lead.phone   (welcome message to lead)

    All failures are silently logged — never raises, never blocks lead save.

    Returns dict with results or None if not configured/enabled.
    """
    try:
        # 1. Load config
        cfg_wa   = WhatsAppConfig.query.filter_by(admin_id=admin_id, is_active=True).first()
        cfg_auto = WALeadAssignConfig.query.filter_by(admin_id=admin_id).first()

        if not cfg_wa or not cfg_auto or not cfg_auto.is_enabled:
            return None  # Not set up — skip silently

        # Check admin subscription
        admin = Admin.query.get(admin_id)
        if not admin or not admin.is_active or admin.is_expired():
            return None

        from app.services.whatsapp_service import BrandmoService
        svc = BrandmoService(cfg_wa)

        # Build substitution context
        context = {
            "lead_name":   lead.name   or "",
            "lead_phone":  lead.phone  or "",
            "lead_source": lead.source or "",
            "agent_name":  agent.name  if agent else "",
            "agent_phone": agent.phone if agent else "",
        }

        results = {}

        # ── Send to AGENT ──────────────────────────────────
        agent_phone_e164 = normalize_phone(agent.phone) if (agent and agent.phone) else ""
        if cfg_auto.agent_template_name and agent and agent_phone_e164:
            try:
                tmpl = WATemplate.query.filter_by(
                    admin_id=admin_id,
                    name=cfg_auto.agent_template_name,
                ).first()
                if tmpl and tmpl.status.upper() == "APPROVED":
                    params  = _resolve_params(cfg_auto.agent_params, context)
                    result  = svc.send_template(
                        agent_phone_e164,
                        tmpl.name,
                        tmpl.language or "en",
                        params,
                    )
                    wamid   = (result.get("messages") or [{}])[0].get("id")
                    contact = get_or_create_contact(admin_id, agent_phone_e164,
                                                    profile_name=agent.name)
                    conv    = get_or_create_conversation(admin_id, contact.id)
                    body_preview = tmpl.body_text or tmpl.name
                    for i, v in enumerate(params, start=1):
                        body_preview = body_preview.replace(f"{{{{{i}}}}}", v)
                    # Only persist message when Brandmo returned a real wamid
                    if wamid:
                        msg = WAMessage(
                            conversation_id = conv.id,
                            admin_id        = admin_id,
                            whatsapp_msg_id = wamid,
                            sender_type     = "system",
                            message_type    = "template",
                            message_text    = body_preview,
                            template_name   = tmpl.name,
                            status          = "sent",
                        )
                        db.session.add(msg)
                    conv.last_message_at = datetime.utcnow()
                    db.session.commit()
                    results["agent"] = {"status": "sent", "wamid": wamid}
                else:
                    results["agent"] = {"status": "skipped",
                                        "reason": "template not found or not APPROVED"}
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[LeadAssign WA] Agent send failed (admin={admin_id}): {e}"
                )
                results["agent"] = {"status": "error", "detail": str(e)}
        else:
            results["agent"] = {"status": "skipped",
                                 "reason": "no agent template, no agent, or agent phone invalid"}

        # ── Send to LEAD ───────────────────────────────────
        lead_phone_e164 = normalize_phone(lead.phone) if lead.phone else ""
        if cfg_auto.lead_template_name and lead_phone_e164:
            try:
                tmpl = WATemplate.query.filter_by(
                    admin_id=admin_id,
                    name=cfg_auto.lead_template_name,
                ).first()
                if tmpl and tmpl.status.upper() == "APPROVED":
                    params  = _resolve_params(cfg_auto.lead_params, context)
                    result  = svc.send_template(
                        lead_phone_e164,
                        tmpl.name,
                        tmpl.language or "en",
                        params,
                    )
                    wamid   = (result.get("messages") or [{}])[0].get("id")
                    contact = get_or_create_contact(admin_id, lead_phone_e164,
                                                    profile_name=lead.name,
                                                    lead_id=lead.id)
                    conv    = get_or_create_conversation(admin_id, contact.id)
                    body_preview = tmpl.body_text or tmpl.name
                    for i, v in enumerate(params, start=1):
                        body_preview = body_preview.replace(f"{{{{{i}}}}}", v)
                    # Only persist message when Brandmo returned a real wamid
                    if wamid:
                        msg = WAMessage(
                            conversation_id = conv.id,
                            admin_id        = admin_id,
                            whatsapp_msg_id = wamid,
                            sender_type     = "system",
                            message_type    = "template",
                            message_text    = body_preview,
                            template_name   = tmpl.name,
                            status          = "sent",
                        )
                        db.session.add(msg)
                    conv.last_message_at = datetime.utcnow()
                    db.session.commit()
                    results["lead"] = {"status": "sent", "wamid": wamid}
                else:
                    results["lead"] = {"status": "skipped",
                                       "reason": "template not found or not APPROVED"}
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[LeadAssign WA] Lead send failed (admin={admin_id}): {e}"
                )
                results["lead"] = {"status": "error", "detail": str(e)}
        else:
            results["lead"] = {"status": "skipped",
                                "reason": "no lead template or lead phone invalid"}

        return results

    except Exception as e:
        current_app.logger.warning(
            f"[LeadAssign WA] Outer error (admin={admin_id}): {e}"
        )
        return None


# ─────────────────────────────────────────────────────────
# 12. LEAD ASSIGN CONFIG — GET / SAVE
# ─────────────────────────────────────────────────────────

@bp.route("/lead-assign-config", methods=["GET"])
@jwt_required()
def get_lead_assign_config():
    """Get the current auto-WhatsApp-on-assignment config for this admin."""
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    cfg = WALeadAssignConfig.query.filter_by(admin_id=admin.id).first()
    return jsonify({"config": cfg.to_dict() if cfg else None}), 200


@bp.route("/lead-assign-config", methods=["POST"])
@jwt_required()
def save_lead_assign_config():
    """
    Save/update the auto-WhatsApp-on-assignment config.

    Body (all optional):
      is_enabled          bool
      agent_template_name str   — APPROVED template name to send to agent
      agent_params        list  — param strings, may include {{lead_name}} etc.
      lead_template_name  str   — APPROVED template name to send to lead
      lead_params         list  — param strings
    """
    if not admin_required():
        return jsonify({"error": "Admin role required"}), 403
    admin, err = get_admin_or_err()
    if err:
        return err

    data = request.get_json() or {}

    cfg = WALeadAssignConfig.query.filter_by(admin_id=admin.id).first()
    if not cfg:
        cfg = WALeadAssignConfig(admin_id=admin.id)
        db.session.add(cfg)

    if "is_enabled" in data:
        cfg.is_enabled = bool(data["is_enabled"])
    if "agent_template_name" in data:
        cfg.agent_template_name = (data["agent_template_name"] or "").strip() or None
    if "agent_params" in data:
        cfg.agent_params = data["agent_params"] if isinstance(data["agent_params"], list) else []
    if "lead_template_name" in data:
        cfg.lead_template_name = (data["lead_template_name"] or "").strip() or None
    if "lead_params" in data:
        cfg.lead_params = data["lead_params"] if isinstance(data["lead_params"], list) else []

    db.session.commit()
    return jsonify({"message": "Config saved", "config": cfg.to_dict()}), 200
