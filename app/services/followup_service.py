from app.models import db, Followup, User, now
from app.services.notification_service import NotificationService
import logging
from datetime import datetime, timedelta

class FollowupService:
    @staticmethod
    def process_scheduled_reminders(app):
        """
        Scheduled Job: Checks for due followups and sends notifications.
        """
        with app.app_context():
            logger = logging.getLogger(__name__)
            # logger.info("Checking for due followups...")
            
            try:
                # Find due, pending, unnotified followups
                # Use UTC for comparison if date_time is UTC, or convert.
                # Assuming date_time is naive local time (as seen in routes/followup.py), we compare with datetime.now()
                # Use a small buffer (e.g. check last 30 mins) to avoid huge backlogs on restart? 
                # Or just check all <= now.
                
                due_time = datetime.now()
                
                pending_reminders = Followup.query.filter(
                    Followup.status == 'pending',
                    Followup.notified == False,
                    Followup.date_time <= due_time
                ).all()
                
                if not pending_reminders:
                    return

                logger.info(f"Found {len(pending_reminders)} due followups.")

                for reminder in pending_reminders:
                    agent = User.query.get(reminder.user_id)
                    if not agent or not agent.phone:
                        continue
                        
                    # Prepare Message
                    params = {
                        "agent_name": agent.name,
                        "contact_name": reminder.contact_name or "Client",
                        "phone": reminder.phone,
                        "time": reminder.date_time.strftime("%I:%M %p"),
                        "message": reminder.message or "No notes"
                    }
                    
                    # Send Notification (WhatsApp)
                    # Template: "followup_reminder"
                    sent = NotificationService.send_whatsapp(agent.phone, "followup_reminder", params)
                    
                    if sent:
                        reminder.notified = True
                        logger.info(f"Reminder {reminder.id} sent to Agent {agent.id}")
                    else:
                        # Maybe retry later? 
                        # For now, we leave notified=False so it retries next cycle
                        pass
                
                db.session.commit()

            except Exception as e:
                logger.error(f"Error in process_scheduled_reminders: {e}")
                db.session.rollback()

def scheduled_followup_job(app):
    FollowupService.process_scheduled_reminders(app)
