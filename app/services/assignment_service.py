from app.models import db, User, Lead, Campaign, now
from app.services.notification_service import NotificationService
import logging

class AssignmentService:
    @staticmethod
    def assign_lead_round_robin(lead, admin_id, campaign_id=None):
        """
        Assigns a lead to the next available agent.
        If campaign_id is provided, assigns ONLY to agents in that campaign.
        Otherwise, falls back to all active agents (or fails, depending on strictness).
        """
        logger = logging.getLogger(__name__)

        try:
            # 1. Get Agents Scope
            agents_query = User.query.filter_by(
                admin_id=admin_id,
                status='active',
                is_suspended=False
            )
            
            if campaign_id:
                # Filter by Campaign
                campaign = Campaign.query.get(campaign_id)
                if campaign:
                    # Use relationship: campaign.agents
                    # We need to filter the User query roughly or just use the relationship list
                    # Using join for cleanliness if agents list is large
                    agents_query = agents_query.join(Campaign.agents).filter(Campaign.id == campaign_id)
                else:
                    logger.warning(f"Campaign {campaign_id} not found. Fallback to all agents.")
            
            active_agents = agents_query.order_by(User.id).all()

            if not active_agents:
                logger.warning(f"No active agents found for Admin {admin_id} (Campaign: {campaign_id}). Lead {lead.id} unassigned.")
                return None

            # 2. Determine Next Agent (Round Robin)
            assigned_agent = None
            
            # Find last assigned lead in this SCOPE (Campaign or Admin)
            last_lead_query = Lead.query.filter_by(admin_id=admin_id).filter(Lead.assigned_to.isnot(None))
            
            if campaign_id:
                last_lead_query = last_lead_query.filter_by(campaign_id=campaign_id)
                
            last_assigned_lead = last_lead_query.order_by(Lead.created_at.desc()).first()

            if not last_assigned_lead:
                assigned_agent = active_agents[0]
            else:
                last_agent_id = last_assigned_lead.assigned_to
                agent_ids = [a.id for a in active_agents]

                if last_agent_id in agent_ids:
                    current_idx = agent_ids.index(last_agent_id)
                    next_idx = (current_idx + 1) % len(agent_ids)
                    assigned_agent = active_agents[next_idx]
                else:
                    assigned_agent = active_agents[0]

            # 3. Assign
            lead.assigned_to = assigned_agent.id
            lead.assigned_agent_name = assigned_agent.name
            lead.assignment_time = now() 
            db.session.commit()
            
            logger.info(f"Lead {lead.id} assigned to Agent {assigned_agent.name} (ID: {assigned_agent.id}) in Campaign {campaign_id}")

            # 4. Notify
            AssignmentService.notify_agent(assigned_agent, lead)

            return assigned_agent

        except Exception as e:
            logger.error(f"Assignment Failed for Lead {lead.id}: {e}")
            return None

    @staticmethod
    def notify_agent(agent, lead):
        try:
            subject = "New Lead Assigned!"
            html_content = f"""
            <h3>New Lead</h3>
            <p>Source: {lead.source} ({lead.campaign.name if lead.campaign else 'General'})</p>
            <p>Name: {lead.name}</p>
            <p>Phone: {lead.phone}</p>
            """
            # NotificationService.send_email(agent.email, subject, html_content)
            
            # Send WhatsApp
            # if agent.phone:
            #     params = {
            #         "agent_name": agent.name,
            #         "lead_source": lead.source,
            #         "lead_name": lead.name,
            #         "lead_phone": lead.phone
            #     }
            #     NotificationService.send_whatsapp(agent.phone, "new_lead_assigned", params)

            # TODO: Implement Push Notification (FCM) here
            # NotificationService.send_push(agent.id, "New Lead", f"New lead assigned: {lead.name}")
            logging.info(f"Notification suppressed (Email/WhatsApp disabled). Push not yet configured.")
                
        except Exception as e:
            logging.error(f"Failed to notify agent {agent.id}: {e}")
