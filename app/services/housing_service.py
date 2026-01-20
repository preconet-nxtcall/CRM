
import imaplib
import email
import re
import datetime
from email.header import decode_header
from app.models import db, HousingSettings, ProcessedEmail, Lead, Admin, now
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

def parse_housing_email_body(body):
    """
    Parses Housing.com email body using Regex.
    Expected format often includes labels.
    """
    # Normalize
    text = body.replace("\r", "").strip()
    
    data = {
        "source": "HOUSING",
        "category": "REAL_ESTATE"
    }

    # Common Patterns for Housing.com
    # Name : John Doe | Mobile : 9876543210 | Email : ...
    

    patterns = {
        "name": r"(?:Name|Customer Name)\s*[:\-]+\s*(.*)",
        "phone": r"(?:Mobile|Phone|Contact|Mobile No)\s*[:\-]+\s*(?:\+91-?)?(\d+)",
        "email": r"(?:Email|Email ID)\s*[:\-]+\s*(.*)",
        "location": r"(?:City|Location)\s*[:\-]+\s*(.*)",
        "project": r"(?:Project|Property)\s*[:\-]+\s*(.*)",
        "budget": r"(?:Budget)\s*[:\-]+\s*(.*)"
    }

    found_any = False
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            # Clean up phone
            if key == "phone":
                val = val.replace("-", "").replace(" ", "")[-10:] # Last 10 digits
            
            # Clean up others (remove pipes using split if needed, though Housing usually uses newlines)
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

def process_single_email(admin_id, msg_id, email_message):
    """
    Parses and saves a single email
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
        lead_data = parse_housing_email_body(body)
        if not lead_data:
            return {"status": "ignored", "reason": "parsing_failed_or_not_lead"}

        # Business Logic Deduplication
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        duplicate_lead = Lead.query.filter(
            Lead.admin_id == admin_id,
            Lead.phone == lead_data.get("phone"),
            Lead.source == "housing",
            Lead.created_at >= today_start
        ).first()

        if duplicate_lead:
             # Mark processed
            pe = ProcessedEmail(admin_id=admin_id, message_id=msg_id, lead_source="HOUSING")
            db.session.add(pe)
            db.session.commit()
            return {"status": "skipped", "reason": "duplicate_lead_today"}

        # Create Lead
        # Store Project in Requirement if available
        requirement_text = lead_data.get("project") or "Residential Property"
        if lead_data.get("budget"):
            requirement_text += f" (Budget: {lead_data.get('budget')})"

        new_lead = Lead(
            admin_id=admin_id,
            name=lead_data.get("name") or "Unknown Housing Caller",
            email=lead_data.get("email"),
            phone=lead_data.get("phone"),
            source="housing",
            status="new",
            location=lead_data.get("location"),
            requirement=requirement_text, # Store Project + Budget
            budget=lead_data.get("budget"),
            custom_fields={"raw_subject": email_message.get("Subject")}
        )

        # ---------------------------------------------------------
        # AGENT ASSIGNMENT LOGIC (ROUND ROBIN)
        # ---------------------------------------------------------
        assigned_user_id = None
        try:
            from app.models import User 
            active_agents = User.query.filter_by(
                admin_id=admin_id, 
                status='active',
                is_suspended=False
            ).order_by(User.id).all()

            if active_agents:
                last_lead = Lead.query.filter_by(admin_id=admin_id)\
                    .filter(Lead.assigned_to.isnot(None))\
                    .order_by(Lead.created_at.desc())\
                    .first()

                if not last_lead or not last_lead.assigned_to:
                    assigned_user_id = active_agents[0].id
                else:
                    last_agent_id = last_lead.assigned_to
                    agent_ids = [agent.id for agent in active_agents]
                    
                    if last_agent_id in agent_ids:
                        current_index = agent_ids.index(last_agent_id)
                        next_index = (current_index + 1) % len(agent_ids)
                        assigned_user_id = agent_ids[next_index]
                    else:
                        assigned_user_id = agent_ids[0]
        except Exception as e:
            logger.error(f"Error in assignment logic for Housing lead: {e}")
        
        if assigned_user_id:
            new_lead.assigned_to = assigned_user_id
        
        db.session.add(new_lead)
        
        pe = ProcessedEmail(admin_id=admin_id, message_id=msg_id, lead_source="HOUSING")
        db.session.add(pe)
        
        db.session.commit()
        return {"status": "success", "lead_id": new_lead.id}

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error processing email {msg_id}: {e}")
        return {"status": "error", "error": str(e)}

def sync_housing_leads(admin_id):
    """
    Main entry point to sync leads for an admin
    """
    settings = HousingSettings.query.filter_by(admin_id=admin_id, is_active=True).first()
    if not settings or not settings.email_id:
        return {"status": "error", "message": "Housing not configured"}

    mail = None
    count = 0
    try:
        mail = get_imap_connection(settings)
        mail.select("inbox")

        # Search for UNSEEN emails from Housing
        # Often from "leads@housing.com" or similar. Case insensitive.
        # We will use SUBJECT "Housing" or FROM "housing" as a broad filter first
        status, messages = mail.search(None, '(UNSEEN (OR FROM "housing" SUBJECT "housing"))')
        
        email_ids = messages[0].split()
        
        for eid in email_ids[-50:]: 
            status, msg_data = mail.fetch(eid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    try:
                        msg = email.message_from_bytes(response_part[1])
                        msg_id = msg.get("Message-ID") or f"no_id_{eid.decode()}"
                        
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

def scheduled_housing_job(app):
    """
    Job to run periodically
    """
    with app.app_context():
        settings_list = HousingSettings.query.filter_by(is_active=True).all()
        print(f"[{datetime.datetime.now()}] Starting Housing Scheduled Sync for {len(settings_list)} accounts...")
        for setting in settings_list:
            try:
                print(f"Syncing Housing for Admin ID: {setting.admin_id}")
                sync_housing_leads(setting.admin_id)
            except Exception as e:
                print(f"Error syncing Housing for Admin {setting.admin_id}: {e}")
