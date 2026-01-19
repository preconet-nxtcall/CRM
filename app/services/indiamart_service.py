from app.models import db, IndiamartSettings, Lead, User, now
import requests
import datetime
import logging

def sync_admin_leads(admin_id):
    """
    Syncs leads for a specific admin from IndiaMART.
    Returns a dict with result stats or error.
    """
    logger = logging.getLogger(__name__)
    
    try:
        settings = IndiamartSettings.query.filter_by(admin_id=admin_id).first()
        if not settings:
            return {"error": "IndiaMART not connected", "status": "skipped"}

        # Decrypt API Key
        glusr_mobile_key = settings.get_api_key()
        if not glusr_mobile_key:
             return {'error': 'Invalid API configuration (Encryption Error)', "status": "error"}
        
        # Prepare API Request
        api_url = "https://api.indiamart.com/wservce/crm/crmListing/v2/"
        
        params = {
            "glusr_mobile": settings.mobile_number,
            "glusr_mobile_key": glusr_mobile_key,
        }
        
        # Incremental Sync: Use last_sync_time if available
        if settings.last_sync_time:
            # Add small buffer to avoid missing leads on the boundary
            start_time = settings.last_sync_time - datetime.timedelta(minutes=5)
            # Python strftime %b is Jan, Feb...
            params["start_time"] = start_time.strftime("%d-%b-%Y %H:%M:%S")
            params["end_time"] = now().strftime("%d-%b-%Y %H:%M:%S")

        logger.info(f"Syncing IndiaMART for Admin {admin_id} with params: {params}")

        # Call IndiaMART
        resp = requests.post(api_url, json=params, timeout=30)
        
        if resp.status_code != 200:
            return {"error": f"IndiaMART API Error: {resp.status_code}", "details": resp.text, "status": "error"}

        data = resp.json()
        
        if data.get("STATUS") != "SUCCESS":
             # Handle "No Data Found" gracefully
             if data.get("CODE") == "404" or "No Data Found" in str(data.get("MESSAGE", "")):
                  # Update sync time anyway so we don't keep polling old range forever
                  settings.last_sync_time = now()
                  db.session.commit()
                  return {"message": "No new leads found", "count": 0, "status": "success"}
             
             return {"error": f"IndiaMART Error: {data.get('MESSAGE')}", "status": "error"}

        leads_list = data.get("RESPONSE", [])
        added_count = 0
        
        for item in leads_list:
            # Extract Fields
            query_id = item.get("UNIQUE_QUERY_ID")
            sender_name = item.get("SENDER_NAME")
            sender_mobile = item.get("SENDER_MOBILE")
            sender_email = item.get("SENDER_EMAIL")
            subject = item.get("SUBJECT")
            message = item.get("QUERY_MESSAGE")
            sender_company = item.get("SENDER_COMPANY")
            sender_city = item.get("SENDER_CITY")
            sender_state = item.get("SENDER_STATE")
            
            im_id = f"IM_{query_id}"
            
            existing = Lead.query.filter_by(facebook_lead_id=im_id, admin_id=admin_id).first()
            if existing:
                continue
                
            # ---------------------------------------------------------
            # ASSIGNMENT LOGIC
            # ---------------------------------------------------------
            assigned_user_id = None
            try:
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
                            assigned_user_id = active_agents[0].id
            except Exception:
                pass # Assignment failed, leave unassigned

            # Create Lead
            new_lead = Lead(
                admin_id=admin_id,
                facebook_lead_id=im_id, 
                name=sender_name,
                email=sender_email,
                phone=sender_mobile,
                source="indiamart",
                status="new",
                assigned_to=assigned_user_id,
                custom_fields={
                    "subject": subject,
                    "message": message,
                    "company": sender_company,
                    "city": sender_city,
                    "state": sender_state,
                    "indiamart_id": query_id
                },
                created_at=now()
            )
            
            db.session.add(new_lead)
            added_count += 1
            
        settings.last_sync_time = now()
        db.session.commit()
        
        return {
            "message": "Sync complete",
            "added": added_count,
            "total_fetched": len(leads_list),
            "status": "success"
        }

    except Exception as e:
        db.session.rollback()
        logger.error(f"IndiaMART Sync Exception: {e}")
        return {"error": str(e), "status": "error"}

def scheduled_sync_job(app):
    """
    Background job to sync leads for all enabled admins.
    Requires 'app' context since it runs in a background thread.
    """
    with app.app_context():
        logger = logging.getLogger(__name__)
        logger.info("Running IndiaMART Scheduled Sync...")
        
        # Find all admins with auto-sync enabled
        # Join with Admin table to ensure admin is active? 
        # For now, just check settings.
        settings_list = IndiamartSettings.query.filter_by(auto_sync_enabled=True).all()
        
        count = 0
        for setting in settings_list:
            try:
                # Check if admin is active?
                admin = Admin.query.get(setting.admin_id)
                if not admin or not admin.is_active:
                    continue
                
                # Run Sync
                result = sync_admin_leads(setting.admin_id)
                if result.get("status") == "success" and result.get("added", 0) > 0:
                     count += result.get("added")
                     logger.info(f"Auto-Sync for Admin {setting.admin_id}: +{result.get('added')} leads")
            except Exception as e:
                logger.error(f"Auto-Sync Failed for Admin {setting.admin_id}: {e}")
        
        logger.info(f"IndiaMART Scheduled Sync Complete. Total Leads Added: {count}")
