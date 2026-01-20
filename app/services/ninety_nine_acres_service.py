
import imaplib
import email
import re
import datetime
from email.header import decode_header
from app.models import db, NinetyNineAcresSettings, ProcessedEmail, Lead, Admin, now
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

def parse_99acres_email_body(body):
    """
    Parses 99acres email body using Regex.
    Returns dict or None.
    """
    # Normalize
    text = body.replace("\r", "").strip()
    
    # Required Markers (Validation) - 99acres usually sends subjects like "You have a new response" or "Enquiry from for..."
    # We will accept if we can find at least a name and phone number and some indication it's real estate related or just rely on the sender (which is filtered in the sync function)
    
    data = {
        "source": "99ACRES",
        "category": "REAL_ESTATE"
    }

    # Common Patterns in 99acres emails
    # Note: These patterns are best guesses based on typical formats. 
    # Real emails might vary: "Name : John Doe", "Mobile : 9876543210"
    patterns = {
        "name": r"(?:Name|Sender Name)\s*[:\-]?\s*(.*)",

        "phone": r"(?:Mobile|Phone|Contact)\s*[:\-]?\s*(?:\+91-?)?(\d+)",
        "email": r"(?:Email ID|Email)\s*[:\-]?\s*(.*)",
        "property_type": r"Property\s*[:\-]?\s*(.*)",
        "project": r"Project\s*[:\-]?\s*(.*)",
        "location": r"Location\s*[:\-]?\s*(.*)"
    }

    found_any = False
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            # Clean up
            if key == "phone":
                val = val.replace("-", "").replace(" ", "")[-10:] # Last 10 digits
            data[key] = val
            found_any = True

    # Fallback: Sometimes emails are just text dumps.
    # If we didn't find specific fields, try to find a phone number at least
    if not data.get("phone"):
         phone_match = re.search(r"[0-9]{10}", text)
         if phone_match:
             data["phone"] = phone_match.group(0)
             found_any = True

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
        lead_data = parse_99acres_email_body(body)
        if not lead_data:
            return {"status": "ignored", "reason": "parsing_failed_or_not_lead"}

        # Business Logic Deduplication (Phone + Source + Today)
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        duplicate_lead = Lead.query.filter(
            Lead.admin_id == admin_id,
            Lead.phone == lead_data.get("phone"),
            Lead.source == "99acres",
            Lead.created_at >= today_start
        ).first()

        if duplicate_lead:
            # Mark processed but don't create lead
            pe = ProcessedEmail(admin_id=admin_id, message_id=msg_id, lead_source="99ACRES")
            db.session.add(pe)
            db.session.commit()
            return {"status": "skipped", "reason": "duplicate_lead_today"}

        # Create Lead
        # Combine Project + Location for Location field
        loc_str = lead_data.get("location", "")
        if lead_data.get("project"):
            loc_str = f"{lead_data.get('project')}, {loc_str}"

        new_lead = Lead(
            admin_id=admin_id,
            name=lead_data.get("name") or "Unknown Buyer",
            email=lead_data.get("email"),
            phone=lead_data.get("phone"),
            source="99acres",
            status="new",
            property_type=lead_data.get("property_type"),
            location=loc_str.strip(' ,'),
            budget=lead_data.get("budget"), # Parser might not catch this yet
            requirement=lead_data.get("requirement"),
            custom_fields={"raw_subject": email_message.get("Subject")}
        )

        # ---------------------------------------------------------
        # AGENT ASSIGNMENT LOGIC (ROUND ROBIN)
        # ---------------------------------------------------------
        assigned_user_id = None
        try:
            # 1. Get all active users (users) for this Admin
            from app.models import User 
            
            active_agents = User.query.filter_by(
                admin_id=admin_id, 
                status='active',
                is_suspended=False
            ).order_by(User.id).all()

            if active_agents:
                # 2. Find the last assigned lead for this admin to determine sequence
                last_lead = Lead.query.filter_by(admin_id=admin_id)\
                    .filter(Lead.assigned_to.isnot(None))\
                    .order_by(Lead.created_at.desc())\
                    .first()

                if not last_lead or not last_lead.assigned_to:
                    # No previous assignment, assign to first agent
                    assigned_user_id = active_agents[0].id
                else:
                    # Find index of last agent
                    last_agent_id = last_lead.assigned_to
                    
                    # Check if last agent is still in the active list
                    agent_ids = [agent.id for agent in active_agents]
                    
                    if last_agent_id in agent_ids:
                        current_index = agent_ids.index(last_agent_id)
                        next_index = (current_index + 1) % len(agent_ids)
                        assigned_user_id = agent_ids[next_index]
                    else:
                        # Last agent removed/inactive, start over
                        assigned_user_id = agent_ids[0]
            
        except Exception as e:
            logger.error(f"Error in assignment logic for 99acres lead: {e}")
        
        if assigned_user_id:
            new_lead.assigned_to = assigned_user_id
        
        db.session.add(new_lead)
        
        # Mark Processed
        pe = ProcessedEmail(admin_id=admin_id, message_id=msg_id, lead_source="99ACRES")
        db.session.add(pe)
        
        db.session.commit()
        return {"status": "success", "lead_id": new_lead.id}

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error processing email {msg_id}: {e}")
        return {"status": "error", "error": str(e)}

def sync_99acres_leads(admin_id):
    """
    Main entry point to sync leads for an admin
    """
    settings = NinetyNineAcresSettings.query.filter_by(admin_id=admin_id, is_active=True).first()
    if not settings or not settings.email_id:
        return {"status": "error", "message": "99acres not configured"}

    mail = None
    count = 0
    try:
        mail = get_imap_connection(settings)
        mail.select("inbox")

        # Search for UNSEEN emails from 99acres
        # Usually from "inquiry@99acres.com" or similar.
        # Broader search: SUBJECT "Enquiry" OR FROM "99acres"
        status, messages = mail.search(None, '(UNSEEN (OR FROM "99acres" SUBJECT "99acres"))')
        
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


def scheduled_99acres_job(app):
    """
    Job to run periodically to sync all active 99acres accounts
    """
    with app.app_context():
        # Get all admins with active settings
        settings_list = NinetyNineAcresSettings.query.filter_by(is_active=True).all()
        
        print(f"[{datetime.datetime.now()}] Starting 99acres Scheduled Sync for {len(settings_list)} accounts...")
        
        for setting in settings_list:
            try:
                print(f"Syncing 99acres for Admin ID: {setting.admin_id}")
                sync_99acres_leads(setting.admin_id)
            except Exception as e:
                print(f"Error syncing 99acres for Admin {setting.admin_id}: {e}")

