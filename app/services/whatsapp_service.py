# app/services/whatsapp_service.py
"""
BrandmoService — Wrapper around Brandmo WhatsApp Cloud API.
Base URL: https://crmpi.brandmo.in/api/meta
Version:  v19.0
"""

import requests
import re
from datetime import datetime
from flask import current_app


class BrandmoService:
    """All calls go through this class so we have one place to change if the API changes."""

    def __init__(self, config):
        """
        config: WhatsAppConfig model instance.
        Resolves base_url and version from Flask app config.
        """
        self.config = config
        try:
            base_url = current_app.config.get("BRANDMO_BASE_URL", "https://crmpi.brandmo.in/api/meta")
            version  = current_app.config.get("BRANDMO_API_VERSION", "v19.0")
        except RuntimeError:
            # Outside app context — use defaults
            base_url = "https://crmpi.brandmo.in/api/meta"
            version  = "v19.0"

        normalized_base, normalized_version = self._normalize_base_and_version(base_url, version)
        self.base      = f"{normalized_base}/{normalized_version}"
        self.token     = config.get_token()
        self.phone_id  = config.phone_number_id
        self.waba_id   = config.waba_id
        self._validate_required_config()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    @staticmethod
    def _normalize_base_and_version(base_url: str, version: str):
        """
        Normalize Brandmo base URL so misconfigured env values still resolve correctly.
        Supports values like:
          - https://crmpi.brandmo.in
          - https://crmpi.brandmo.in/api/meta
          - https://crmpi.brandmo.in/api/meta/v19.0
        """
        raw_base = (base_url or "https://crmpi.brandmo.in/api/meta").strip().rstrip("/")
        raw_version = (version or "v19.0").strip()

        # Accept host-only config by attaching default scheme.
        if raw_base and "://" not in raw_base:
            raw_base = f"https://{raw_base}"

        # If version is included in base url, extract and keep only /api/meta in base.
        m = re.search(r"/(v\d+(?:\.\d+)?)$", raw_base)
        if m:
            raw_version = m.group(1)
            raw_base = raw_base[: -(len(raw_version) + 1)]

        # Ensure Brandmo meta path exists even when BRANDMO_BASE_URL is host-only.
        if "/api/meta" not in raw_base:
            raw_base = f"{raw_base}/api/meta"

        return raw_base.rstrip("/"), raw_version

    def _msg_url(self):
        """Messages endpoint."""
        return f"{self.base}/{self.phone_id}/messages"

    def _validate_required_config(self):
        missing = []
        if not self.token:
            missing.append("access_token")
        if not (self.phone_id or "").strip():
            missing.append("phone_number_id")
        if not (self.waba_id or "").strip():
            missing.append("waba_id")
        if missing:
            raise ValueError(
                f"WhatsApp configuration is incomplete. Missing: {', '.join(missing)}"
            )

    @staticmethod
    def _json_or_raise(response: requests.Response, context: str) -> dict:
        try:
            return response.json()
        except Exception:
            short_text = (response.text or "")[:200].replace("<", "&lt;").replace(">", "&gt;")
            raise ValueError(
                f"Brandmo returned a non-JSON response for {context}. "
                f"Status: {response.status_code}. Response preview: {short_text}..."
            )

    # ------------------------------------------------------------------
    # SEND TEXT MESSAGE (session window)
    # ------------------------------------------------------------------
    def send_text(self, phone: str, text: str) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                phone,
            "type":              "text",
            "text":              {"body": text},
        }
        r = requests.post(self._msg_url(), json=payload, headers=self._headers(), timeout=20)
        r.raise_for_status()
        return self._json_or_raise(r, "send_text")

    # ------------------------------------------------------------------
    # SEND TEMPLATE MESSAGE
    # ------------------------------------------------------------------
    def send_template(self, phone: str, template_name: str, language: str,
                      parameters: list = None, header: dict = None) -> dict:
        """
        parameters: list of str values for {{1}}, {{2}}, ... body variables.
        header: dict representing the header, e.g. {"type": "IMAGE", "image": {"link": "..."}}
        Builds a standard body-parameter template payload.
        """
        components = []
        if header:
            # We enforce standard format if it's missing the "parameters" wrapper
            components.append({
                "type": "header",
                "parameters": [header] if "type" in header else header.get("parameters", [])
            })
            
        if parameters:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in parameters],
            })

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                phone,
            "type":              "template",
            "template": {
                "language": {"policy": "deterministic", "code": language},
                "name":     template_name,
            },
        }
        
        # Meta API throws validation errors if components is an empty list
        if components:
            payload["template"]["components"] = components

        r = requests.post(self._msg_url(), json=payload, headers=self._headers(), timeout=20)
        r.raise_for_status()
        return self._json_or_raise(r, "send_template")

    # ------------------------------------------------------------------
    # SEND MEDIA MESSAGE (Direct format outside template)
    # ------------------------------------------------------------------
    def send_media(self, phone: str, media_type: str, media_link: str = None, 
                   media_id: str = None, caption: str = None, filename: str = None) -> dict:
        """
        media_type: image, video, audio, document
        media_link: URL to public media file
        media_id: ID returned from Meta Media upload
        Requires 24-hour conversational window.
        """
        if media_type not in ["image", "video", "audio", "document"]:
            raise ValueError(f"Unsupported media type: {media_type}")
            
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                phone,
            "type":              media_type,
            media_type:          {}
        }
        
        if media_link:
            payload[media_type]["link"] = media_link
        elif media_id:
            payload[media_type]["id"] = media_id
        else:
            raise ValueError("Either media_link or media_id must be provided")

        if caption and media_type in ["image", "video", "document"]:
            payload[media_type]["caption"] = caption
            
        if filename and media_type == "document":
            payload[media_type]["filename"] = filename

        r = requests.post(self._msg_url(), json=payload, headers=self._headers(), timeout=20)
        r.raise_for_status()
        return self._json_or_raise(r, "send_media")

    # ------------------------------------------------------------------
    # SYNC TEMPLATES FROM BRANDMO → DB
    # ------------------------------------------------------------------
    def sync_templates(self) -> int:
        """
        Fetch all approved templates from Brandmo, upsert into wa_templates.
        Returns count of templates synced.
        """
        from app.models import db, WATemplate

        url = f"{self.base}/{self.waba_id}/message_templates"
        params = {"limit": 200}
        templates_data = []
        count = 0

        # Paginate through all templates
        while url:
            r = requests.get(url, headers=self._headers(), params=params, timeout=30)

            # Log raw response for debugging if it's not JSON
            if not r.content:
                current_app.logger.error(
                    f"[WA Sync] Empty response from Brandmo (status {r.status_code})"
                )
                raise ValueError(
                    f"Brandmo returned an empty response (HTTP {r.status_code}). "
                    "Please check your Access Token and WABA ID."
                )

            # Try to parse JSON — Brandmo sometimes returns HTML on auth errors
            try:
                data = r.json()
            except Exception:
                short_text = r.text[:200].replace("<", "&lt;").replace(">", "&gt;")
                current_app.logger.error(
                    f"[WA Sync] Non-JSON response from Brandmo (status {r.status_code}): {r.text[:500]}"
                )
                raise ValueError(
                    f"Brandmo returned an unexpected response (not JSON). "
                    f"Status: {r.status_code}. "
                    f"Requested URL: {url}. "
                    f"Response preview: {short_text}... "
                    "This usually means your Access Token/WABA ID is invalid, or BRANDMO_BASE_URL is misconfigured."
                )

            # Now raise for HTTP errors (after JSON parsed, so we can include the message)
            if not r.ok:
                err_msg = data.get("error", {}).get("message", r.text[:300])
                current_app.logger.error(f"[WA Sync] Brandmo API error: {data}")
                raise requests.HTTPError(
                    f"Brandmo API error ({r.status_code}): {err_msg}",
                    response=r,
                )

            templates_data.extend(data.get("data", []))
            paging = data.get("paging", {})
            next_url = paging.get("next")
            # Stop if next page url is same (avoid infinite loop) or absent
            url = next_url if next_url and next_url != url else None
            params = {}  # next URL already includes params

        for t in templates_data:
            name       = t.get("name")
            language   = t.get("language", "en")
            category   = t.get("category")
            status     = t.get("status", "APPROVED")
            template_id = t.get("id")
            components  = t.get("components", [])

            if not name:
                continue

            # Parse body text and variable count
            body_text      = None
            variable_count = 0
            header_type    = None

            for comp in components:
                comp_type = comp.get("type", "").upper()
                if comp_type == "BODY":
                    body_text = comp.get("text", "")
                    variable_count = len(re.findall(r"\{\{\d+\}\}", body_text or ""))
                elif comp_type == "HEADER":
                    header_type = comp.get("format", "TEXT").upper()

            # Upsert (admin_id + name + language must be unique)
            existing = WATemplate.query.filter_by(
                admin_id=self.config.admin_id,
                name=name,
                language=language,
            ).first()

            now = datetime.utcnow()
            if existing:
                existing.template_id    = template_id
                existing.category       = category
                existing.status         = status
                existing.components     = components
                existing.header_type    = header_type
                existing.body_text      = body_text
                existing.variable_count = variable_count
                existing.synced_at      = now
            else:
                tmpl = WATemplate(
                    admin_id       = self.config.admin_id,
                    template_id    = template_id,
                    name           = name,
                    language       = language,
                    category       = category,
                    status         = status,
                    components     = components,
                    header_type    = header_type,
                    body_text      = body_text,
                    variable_count = variable_count,
                    synced_at      = now,
                )
                db.session.add(tmpl)
            count += 1

        db.session.commit()
        return count

    # ------------------------------------------------------------------
    # CREATE TEMPLATE VIA BRANDMO API
    # ------------------------------------------------------------------
    def create_template(self, name: str, category: str, language: str,
                        components: list) -> dict:
        """
        Submit a new template to Brandmo/Meta for approval.
        components: list of component dicts (HEADER, BODY, FOOTER, BUTTONS).
        """
        url = f"{self.base}/{self.waba_id}/message_templates"
        payload = {
            "name":       name,
            "category":   category.upper(),
            "language":   language,
            "components": components,
        }
        r = requests.post(url, json=payload, headers=self._headers(), timeout=30)
        r.raise_for_status()
        return self._json_or_raise(r, "create_template")

    # ------------------------------------------------------------------
    # DELETE TEMPLATE VIA BRANDMO API
    # ------------------------------------------------------------------
    def delete_template(self, template_name: str) -> dict:
        url = f"{self.base}/{self.waba_id}/message_templates"
        params = {"name": template_name}
        r = requests.delete(url, headers=self._headers(), params=params, timeout=20)
        r.raise_for_status()
        return self._json_or_raise(r, "delete_template")


# ------------------------------------------------------------------
# GLOBAL SCHEDULED SYNC TASK
# ------------------------------------------------------------------
def sync_all_wa_templates(app):
    """
    APScheduler job: sync templates for every admin that has WhatsApp configured.
    Called from app/__init__.py on a schedule.
    """
    with app.app_context():
        from app.models import WhatsAppConfig, Admin
        configs = WhatsAppConfig.query.filter_by(is_active=True).all()
        for cfg in configs:
            try:
                # SaaS: skip expired admins — don't waste API calls on lapsed subscriptions
                admin = Admin.query.get(cfg.admin_id)
                if not admin or not admin.is_active or admin.is_expired():
                    continue
                svc = BrandmoService(cfg)
                if not svc.token or not svc.waba_id:
                    continue
                n = svc.sync_templates()
                print(f"[WA Sync] Admin {cfg.admin_id}: synced {n} templates")
            except Exception as e:
                print(f"[WA Sync] Admin {cfg.admin_id} error: {e}")
