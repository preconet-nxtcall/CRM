import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import db, User, Admin, Lead, Campaign, now
from app.services.lead_service import LeadService
from app.services.campaign_service import CampaignService
from run import app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CampVerify")

def run_verification():
    with app.app_context():
        logger.info("Starting Campaign Verification...")
        suffix = datetime.now().strftime("%H%M%S")
        
        # 1. Setup Admin
        admin = Admin(name=f"Admin {suffix}", email=f"admin_{suffix}@test.com", password_hash="hash", is_active=True)
        db.session.add(admin)
        db.session.commit()

        # 2. Setup Agents
        agent1 = User(name="Agent A", email=f"a_{suffix}@test.com", password_hash="hash", admin_id=admin.id, status="active")
        agent2 = User(name="Agent B", email=f"b_{suffix}@test.com", password_hash="hash", admin_id=admin.id, status="active")
        agent3 = User(name="Agent C", email=f"c_{suffix}@test.com", password_hash="hash", admin_id=admin.id, status="active")
        db.session.add_all([agent1, agent2, agent3])
        db.session.commit()

        # 3. Create Campaigns
        camp_sales = CampaignService.create_campaign(admin.id, "Sales Campaign")
        camp_support = CampaignService.create_campaign(admin.id, "Support Campaign")
        
        logger.info(f"Created Campaigns: Sales={camp_sales.id}, Support={camp_support.id}")

        # 4. Assign Agents to Campaigns
        # Sales: Agent A & B
        CampaignService.update_campaign_agents(camp_sales.id, [agent1.id, agent2.id])
        # Support: Agent C
        CampaignService.update_campaign_agents(camp_support.id, [agent3.id])

        # 5. Ingest Leads and Verify Assignment
        
        # Lead 1 -> Sales (Should go to A or B)
        data1 = {"name": "Sales Lead 1", "phone": "1111111111"}
        lead1 = LeadService.ingest_lead(admin.id, "website", data1, campaign_id=camp_sales.id)
        logger.info(f"Lead 1 (Sales) Assigned to: {lead1.assigned_to}")
        assert lead1.assigned_to in [agent1.id, agent2.id]

        # Lead 2 -> Sales (Should go to the other one)
        data2 = {"name": "Sales Lead 2", "phone": "2222222222"}
        lead2 = LeadService.ingest_lead(admin.id, "website", data2, campaign_id=camp_sales.id)
        logger.info(f"Lead 2 (Sales) Assigned to: {lead2.assigned_to}")
        assert lead2.assigned_to in [agent1.id, agent2.id]
        if lead1.assigned_to == lead2.assigned_to:
            logger.warning("Round Robin might be failing or sequence reset? (Expected A->B)")
        else:
            logger.info("Round Robin OK (A->B)")

        # Lead 3 -> Support (Should go to C)
        data3 = {"name": "Support Lead 1", "phone": "3333333333"}
        lead3 = LeadService.ingest_lead(admin.id, "website", data3, campaign_id=camp_support.id)
        logger.info(f"Lead 3 (Support) Assigned to: {lead3.assigned_to}")
        assert lead3.assigned_to == agent3.id

        # Lead 4 (General) Assigned to: {lead4.assigned_to}")
        # assert lead4.assigned_to in [agent1.id, agent2.id, agent3.id]

        # 6. Verify Magicbricks/99acres logic simulation
        # Simulate what process_single_email does: calls LeadService with specific campaign
        
        # Magicbricks -> Sales
        data_mb = {"name": "MB Lead", "phone": "5555555555", "source": "magicbricks"}
        lead_mb = LeadService.ingest_lead(admin.id, "magicbricks", data_mb, campaign_id=camp_sales.id)
        logger.info(f"Lead MB (Sales) Assigned to: {lead_mb.assigned_to}")
        assert lead_mb.assigned_to in [agent1.id, agent2.id]
        
        # 99acres -> Support (Just for testing routing)
        data_99 = {"name": "99acres Lead", "phone": "6666666666", "source": "99acres"}
        lead_99 = LeadService.ingest_lead(admin.id, "99acres", data_99, campaign_id=camp_support.id)
        logger.info(f"Lead 99acres (Support) Assigned to: {lead_99.assigned_to}")
        assert lead_99.assigned_to == agent3.id
        
        logger.info("Verification Complete.")

if __name__ == "__main__":
    run_verification()
