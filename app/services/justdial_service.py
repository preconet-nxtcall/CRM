
import imaplib
import email
import re
import datetime
from email.header import decode_header
from app.models import db, JustDialSettings, ProcessedEmail, Lead, Admin, now
from app.utils.security import decrypt_value
from sqlalchemy.exc import IntegrityError
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_imap_connection(settings):
    """
    Connect to IMAP server using settings
    """
    try:
        password = settings.get_app_password()
        if not password:
            raise Exception("No App Password configured")

        mail = imaplib.IMAP4_SSL(settings.imap_host)
        mail.login(settings.email_id, password)
        return mail
    except Exception as e:
        logger.error(f"IMAP Connection Failed for {settings.email_id}: {e}")
        raise e

def parse_justdial_email_body(body):
    """
    Parses JustDial email body using Regex.
    Expected format often includes labels.
    """
    # Normalize
    text = body.replace("\r", "").strip()
    
    data = {
        "source": "JUSTDIAL",
        "category": "BUSINESS"
    }

    # Common Patterns
    # JustDial Email structure varies but often:
    # Name : John Doe | Mobile : 9876543210 | Area : ...
    
    patterns = {
        "name": r"(?:Name|Caller Name|Sender)\s*[:\-]?\s*(.*)",
        "phone": r"(?:Mobile|Phone|Contact|Mobile No)\s*[:\-]?\s*(?:\+91-?)?(\d+)",
        "email": r"(?:Email|Email ID)\s*[:\-]?\s*(.*)",
        "location": r"(?:Area|Location|City)\s*[:\-]?\s*(.*)",
        "category": r"(?:Category|Requirement)\s*[:\-]?\s*(.*)",
    }

    found_any = False
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            # Clean up phone
            if key == "phone":
                val = val.replace("-", "").replace(" ", "")[-10:] # Last 10 digits
            
            # Clean up others (sometimes JD emails have pipes | as separators)
            if key != "phone":
                 val = val.split("|")[0].strip()
            
            data[key] = val
            found_any = True

    # Fallback for phone
    if not data.get("phone"):
         phone_match = re.search(r"[0-9]{10}", text)
         if phone_match:
             data["phone"] = phone_match.group(0)
             found_any = True

    # Basic Validation
    if not data.get("phone") and not data.get("email"):
        return None 

    return data

def process_single_email(admin_id, msg_id, email_message, campaign_id=None):
    """
    Parses and saves a single email using LeadService
    """
    try:
        # Check Deduplication by Message-ID
        existing = ProcessedEmail.query.filter_by(admin_id=admin_id, message_id=msg_id).first()
        if existing:
            return {"status": "skipped", "reason": "duplicate_msg_id"}

        # Get Body(Prefer Text)
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    body = part.get_payload(decode=True).decode()
                    break 
        else:
            body = email_message.get_payload(decode=True).decode()

        # Parse
        lead_data = parse_justdial_email_body(body)
        if not lead_data:
            return {"status": "ignored", "reason": "parsing_failed_or_not_lead"}

        # Create Lead
        data = {
            "name": lead_data.get("name") or "Unknown JD Caller",
            "email": lead_data.get("email"),
            "phone": lead_data.get("phone"),
            "source": "justdial",
            "status": "new",
            "location": lead_data.get("location"),
            "requirement": lead_data.get("category"), # Store Category in Requirement
            "custom_fields": {"raw_subject": email_message.get("Subject")}
        }

        # Ingest
        from app.services.lead_service import LeadService
        new_lead = LeadService.ingest_lead(admin_id, "justdial", data, campaign_id=campaign_id)
        
        if not new_lead:
             pass

        if new_lead:
            # Mark Processed
            pe = ProcessedEmail(admin_id=admin_id, message_id=msg_id, lead_source="JUSTDIAL")
            db.session.add(pe)
            db.session.commit()
            return {"status": "success", "lead_id": new_lead.id}
        else:
             return {"status": "skipped", "reason": "validation_failed"}

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error processing email {msg_id}: {e}")
        return {"status": "error", "error": str(e)}

def sync_justdial_leads(admin_id):
    """
    Main entry point to sync leads for an admin
    """
    settings = JustDialSettings.query.filter_by(admin_id=admin_id, is_active=True).first()
    if not settings or not settings.email_id:
        return {"status": "error", "message": "JustDial not configured"}

    mail = None
    count = 0
    try:
        mail = get_imap_connection(settings)
        mail.select("inbox")

        # Search for UNSEEN emails from JustDial
        # Often from "noreply@justdial.com" or Subject "Justdial"
        status, messages = mail.search(None, '(UNSEEN (OR FROM "justdial" SUBJECT "justdial"))')
        
        email_ids = messages[0].split()
        
        for eid in email_ids[-50:]: 
            status, msg_data = mail.fetch(eid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    try:
                        msg = email.message_from_bytes(response_part[1])
                        msg_id = msg.get("Message-ID") or f"no_id_{eid.decode()}"
                        
                        result = process_single_email(admin_id, msg_id, msg, campaign_id=settings.campaign_id)
                        
                        if result["status"] == "success":
                            count += 1
                    except Exception as e:
                        logger.error(f"Failed to parse email ID {eid}: {e}")

        settings.last_sync_time = now()
        db.session.commit()
        
        return {"status": "success", "added": count}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except:
                pass

def scheduled_justdial_job(app):
    """
    Job to run periodically
    """
    with app.app_context():
        settings_list = JustDialSettings.query.filter_by(is_active=True).all()
        print(f"[{datetime.datetime.now()}] Starting JustDial Scheduled Sync for {len(settings_list)} accounts...")
        for setting in settings_list:
            try:
                print(f"Syncing JustDial for Admin ID: {setting.admin_id}")
                sync_justdial_leads(setting.admin_id)
            except Exception as e:
                print(f"Error syncing JustDial for Admin {setting.admin_id}: {e}")
