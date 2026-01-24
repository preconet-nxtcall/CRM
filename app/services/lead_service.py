from app.models import db, Lead, now
from app.services.assignment_service import AssignmentService
import logging
import re

class LeadService:
    @staticmethod
    def normalize_phone(phone_number):
        """
        Standardize phone number to 10 digits for deduplication.
        Removes +91, 0, -, spaces.
        """
        if not phone_number:
            return None
        
        # Remove non-numeric characters
        clean = re.sub(r'\D', '', str(phone_number))
        
        # Extract last 10 digits
        if len(clean) >= 10:
            return clean[-10:]
            
        return clean

    @staticmethod
    def ingest_lead(admin_id, source, data, campaign_id=None):
        """
        Centralized method to Ingest or Update a Lead.
        
        Args:
            admin_id (int): ID of the company/admin.
            source (str): Source name.
            data (dict): Lead data.
            campaign_id (int): Optional Campaign ID to link lead to.
        """
        logger = logging.getLogger(__name__)
        
        try:
            raw_phone = data.get('phone')
            clean_phone = LeadService.normalize_phone(raw_phone)
            
            # Allow lead without phone if email is present (Optional - for now stick to phone requirement or email)
            # if not clean_phone and not data.get('email'):
            if not clean_phone:
                 # Some sources might provide only email? For now require phone.
                 logger.warning(f"Skipping lead from {source}: No valid phone number.")
                 return None

            facebook_lead_id = data.get('facebook_lead_id')
            lead_identifier = data.get('lead_identifier')
            
            # Deduplication Priority: 
            # 1. lead_identifier (Generic Unique ID)
            # 2. facebook_lead_id (Platform ID)
            # 3. Phone Number (Fallback)
       
            existing_lead = None
            
            if lead_identifier:
                existing_lead = Lead.query.filter_by(admin_id=admin_id, lead_identifier=lead_identifier).first()
            
            if not existing_lead and facebook_lead_id:
                existing_lead = Lead.query.filter_by(admin_id=admin_id, facebook_lead_id=facebook_lead_id).first()
                
            if not existing_lead:
                existing_lead = Lead.query.filter_by(admin_id=admin_id, phone=raw_phone).first()

            if existing_lead:
                # Update
                logger.info(f"Duplicate Lead found (ID: {existing_lead.id}). Updating.")
                if data.get('name') and data.get('name') != 'Unknown': existing_lead.name = data.get('name')
                if data.get('email'): existing_lead.email = data.get('email')
                
                # Update sub_source if not set
                if not existing_lead.sub_source and data.get('sub_source'):
                     existing_lead.sub_source = data.get('sub_source')
                
                # Check if we should update campaign? usually stick to original campaign unless specified
                # If lead has no campaign, assign it now
                if not existing_lead.campaign_id and campaign_id:
                    existing_lead.campaign_id = campaign_id
                
                existing_lead.updated_at = now()
                db.session.commit()
                return existing_lead

            else:
                # Create
                new_lead = Lead(
                    admin_id=admin_id,
                    campaign_id=campaign_id,
                    facebook_lead_id=facebook_lead_id,
                    lead_identifier=lead_identifier,
                    form_id=data.get('form_id'),
                    name=data.get('name', 'Unknown'),
                    email=data.get('email'),
                    phone=raw_phone,
                    source=source,
                    sub_source=data.get('sub_source'),
                    status="new",
                    custom_fields=data.get('custom_fields', {}),
                    created_at=now()
                )
                
                db.session.add(new_lead)
                db.session.commit()
                
                # Assign
                AssignmentService.assign_lead_round_robin(new_lead, admin_id, campaign_id)
                
                return new_lead

        except Exception as e:
            logger.error(f"Lead Ingestion Failed: {e}")
            db.session.rollback()
            return None


