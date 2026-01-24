from app.models import db, Campaign, User, Admin, now
import logging

class CampaignService:
    @staticmethod
    def create_campaign(admin_id, name, description=None):
        try:
            campaign = Campaign(
                admin_id=admin_id,
                name=name,
                description=description,
                status="active"
            )
            db.session.add(campaign)
            db.session.commit()
            return campaign
        except Exception as e:
            db.session.rollback()
            logging.error(f"Create Campaign Failed: {e}")
            return None

    @staticmethod
    def update_campaign_agents(campaign_id, agent_ids):
        """
        Update the list of agents assigned to a campaign.
        Replaces existing list.
        """
        try:
            campaign = Campaign.query.get(campaign_id)
            if not campaign:
                return False

            # Fetch Users
            agents = User.query.filter(User.id.in_(agent_ids), User.admin_id == campaign.admin_id).all()
            
            # Update Relationship
            campaign.agents = agents
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logging.error(f"Update Campaign Agents Failed: {e}")
            return False

    @staticmethod
    def get_campaigns(admin_id):
        return Campaign.query.filter_by(admin_id=admin_id).all()
