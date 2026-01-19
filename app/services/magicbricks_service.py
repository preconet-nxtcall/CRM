
import imaplib
import email
import re
import datetime
from email.header import decode_header
from app.models import db, MagicbricksSettings, ProcessedEmail, Lead, Admin, now
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

def parse_email_body(body):
    """
    Parses Magicbricks email body using Regex.
    Returns dict or None.
    """
    # Normalize
    text = body.replace("\r", "").strip()
    
    # Required Markers (Validation)
    if "Magicbricks" not in text and "Buyer Lead" not in text:
        return None

    data = {
        "source": "MAGICBRICKS",
        "category": "REAL_ESTATE"
    }

    # Regex Patterns (Case Insensitive)
    patterns = {
        "name": r"Buyer Name:\s*(.*)",
        "phone": r"Contact Number:\s*(?:\+91-?)?(\d+)",
        "email": r"Email ID:\s*(.*)",
        "property_type": r"Property Type:\s*(.*)",
        "purpose": r"Purpose:\s*(.*)", # Rent/Buy
        "location": r"Location:\s*(.*)",
        "budget": r"Budget:\s*(.*)",
        "requirement": r"Requirement:\s*(.*)"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            # Clean up
            if key == "phone":
                val = val.replace("-", "").replace(" ", "")[-10:] # Last 10 digits
            data[key] = val

    # Basic Validation
    if not data.get("phone") and not data.get("email"):
        return None # Useless lead

    return data

def process_single_email(admin_id, msg_id, email_message):
    """
    Parses and saves a single email
    """
    try:
        # Check Deduplication by Message-ID
        existing = ProcessedEmail.query.filter_by(admin_id=admin_id, message_id=msg_id).first()
        if existing:
            return {"status": "skipped", "reason": "duplicate_msg_id"}

        # Get Body
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    body = part.get_payload(decode=True).decode()
                    break # Prefer text/plain
        else:
            body = email_message.get_payload(decode=True).decode()

        # Parse
        lead_data = parse_email_body(body)
        if not lead_data:
            return {"status": "ignored", "reason": "parsing_failed_or_not_lead"}

        # Business Logic Deduplication (Phone + Property + Today)
        # Prevents same user spamming same requirement
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        duplicate_lead = Lead.query.filter(
            Lead.admin_id == admin_id,
            Lead.phone == lead_data.get("phone"),
            Lead.source == "MAGICBRICKS",
            Lead.created_at >= today_start
        ).first()

        if duplicate_lead:
            # Mark processed but don't create lead
            pe = ProcessedEmail(admin_id=admin_id, message_id=msg_id)
            db.session.add(pe)
            db.session.commit()
            return {"status": "skipped", "reason": "duplicate_lead_today"}

        # Create Lead
        new_lead = Lead(
            admin_id=admin_id,
            name=lead_data.get("name") or "Unknown Buyer",
            email=lead_data.get("email"),
            phone=lead_data.get("phone"),
            source="magicbricks",
            status="new",
            property_type=lead_data.get("property_type"),
            location=lead_data.get("location"),
            budget=lead_data.get("budget"),
            requirement=lead_data.get("requirement"),
            custom_fields={"purpose": lead_data.get("purpose")}
        )
        
        db.session.add(new_lead)
        
        # Mark Processed
        pe = ProcessedEmail(admin_id=admin_id, message_id=msg_id)
        db.session.add(pe)
        
        db.session.commit()
        return {"status": "success", "lead_id": new_lead.id}

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error processing email {msg_id}: {e}")
        return {"status": "error", "error": str(e)}

def sync_magicbricks_leads(admin_id):
    """
    Main entry point to sync leads for an admin
    """
    settings = MagicbricksSettings.query.filter_by(admin_id=admin_id, is_active=True).first()
    if not settings or not settings.email_id:
        return {"status": "error", "message": "Magicbricks not configured"}

    mail = None
    count = 0
    try:
        mail = get_imap_connection(settings)
        mail.select("inbox")

        # Search for UNSEEN emails from Magicbricks
        # Refining search to avoid fetching everything
        # SEARCH UNSEEN FROM "leads@magicbricks.com" (or similar)
        # For generalized solution, search SUBJECT "Buyer Lead"
        status, messages = mail.search(None, '(UNSEEN SUBJECT "Buyer Lead")')
        
        email_ids = messages[0].split()
        
        # Limit to last 50 to prevent timeouts if inbox is huge
        for eid in email_ids[-50:]: 
            status, msg_data = mail.fetch(eid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    try:
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Extract Message-ID
                        msg_id = msg.get("Message-ID") or f"no_id_{eid.decode()}"
                        
                        # Process
                        result = process_single_email(admin_id, msg_id, msg)
                        
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

def scheduled_magicbricks_job(app):
    """
    APScheduler Job
    """
    with app.app_context():
        logger.info("Starting Magicbricks Scheduled Sync...")
        settings_list = MagicbricksSettings.query.filter_by(is_active=True).all()
        
        total = 0
        for s in settings_list:
            try:
                # Check subscription status etc if needed
                res = sync_magicbricks_leads(s.admin_id)
                if res.get("status") == "success":
                    total += res.get("added", 0)
            except Exception as e:
                logger.error(f"Auto-sync failed for admin {s.admin_id}: {e}")
                
        logger.info(f"Magicbricks Sync Complete. Added {total} leads.")
