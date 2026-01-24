
import logging
from flask import current_app

class NotificationService:
    @staticmethod
    def send_email(to_email, subject, html_content):
        """
        Sends an email using ZeptoMail HTTP API.
        """
        try:
            import requests
            
            api_token = current_app.config.get("ZEPTOMAIL_API_TOKEN")
            sender_email = current_app.config.get("ZEPTOMAIL_USER")
            
            if not api_token or not sender_email:
                logging.warning("Skipping Email: ZEPTOMAIL credentials not set.")
                return False

            url = "https://api.zeptomail.in/v1.1/email"
            
            payload = {
                "from": {
                    "address": sender_email
                },
                "to": [{
                    "email_address": {
                        "address": to_email,
                        "name": to_email.split('@')[0]
                    }
                }],
                "subject": subject,
                "htmlbody": html_content
            }
            
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": api_token
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            
            if response.status_code in [200, 201]:
                logging.info(f"Email sent successfully to {to_email}")
                return True
            else:
                logging.error(f"Failed to send email to {to_email}: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logging.error(f"Failed to send email to {to_email}: {e}")
            return False

    @staticmethod
    def send_welcome_notification(name, username, password, expiry_date, email, phone=None):
        """
        Orchestrates sending Welcome Email using the specific HTML template.
        'phone' argument is kept for compatibility but ignored.
        """
        if not email:
            return

        # Format Expiry Date: 05 Dec 2025
        expiry_str = "N/A"
        if expiry_date:
            if hasattr(expiry_date, 'strftime'):
                expiry_str = expiry_date.strftime("%d %b %Y")
            else:
                expiry_str = str(expiry_date)

        # ---------------------------------------------------------
        # EMAIL CONTENT (TEMPLATE)
        # ---------------------------------------------------------
        subject = "Welcome to Nxt Call.app"
        
        # Using the exact template provided
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Welcome to Nxt Call Manager</title>
  <style>
    body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px; }}
    .container {{ max-width: 600px; background: white; padding: 25px; border-radius: 10px;
                 box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
    h2 {{ color: #1a73e8; }}
    .details {{ background: #f1f1f1; padding: 15px; border-radius: 8px; margin-top: 15px; }}
    .footer {{ margin-top: 20px; font-size: 13px; color: #777; }}
  </style>
</head>
<body>

  <div class="container">
    <h2>Welcome to Nxt Call !</h2>

    <p>Hello <strong>{name}</strong>,</p>

    <p>Your account has been successfully created.</p>

    <div class="details">
      <p><strong>Login Details:</strong></p>
      <p>Username: {username}</p>
      <p>Password: {password}</p>
      <p>Account Expiry Date: {expiry_str}</p>
    </div>

    <p>Please download "NxtCall.app" from the Play Store, log in using your credentials, and connect your profile.</p>

    <p>Thank you,<br/>The Nxt CallTeam</p>

    <div class="footer">
      This is an automated email. Please do not reply.
    </div>
  </div>

</body>
</html>
"""

        # ---------------------------------------------------------
        # SEND
        # ---------------------------------------------------------
        return NotificationService.send_email(email, subject, html_content)

    @staticmethod
    def send_password_reset_email(email, reset_link):
        """
        Sends Password Reset Email.
        """
        subject = "Reset Your Password - Nxt Call.app"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 20px; }}
    .btn {{ background-color: #dc2626; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
  </style>
</head>
<body>
  <h2>Password Reset Request</h2>
  <p>We received a request to reset your password.</p>
  <p>Click the button below to reset it:</p>
  <br>
  <a href="{reset_link}" class="btn">Reset Password</a>
  <br><br>
  <p>If you did not request this, please ignore this email.</p>
  <p>Link expires in 15 minutes.</p>
</body>
</html>
"""
        return NotificationService.send_email(email, subject, html_content)

    @staticmethod
    def send_whatsapp(phone, template_name, params=None):
        """
        Sends a WhatsApp message using a provider (e.g., Interakt, Wati, Twilio).
        """
        try:
            import requests
            
            # Configuration (placeholder keys)
            wa_api_url = current_app.config.get("WHATSAPP_API_URL")
            wa_api_key = current_app.config.get("WHATSAPP_API_KEY")
            
            if not wa_api_url or not wa_api_key:
                logging.warning(f"Skipping WhatsApp to {phone}: API Not Configured.")
                return False

            if not phone:
                return False

            payload = {
                "phoneNumber": phone,
                "template": template_name,
                "parameters": params or {}
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {wa_api_key}"
            }
            
            # Fire and forget (with timeout)
            requests.post(wa_api_url, json=payload, headers=headers, timeout=5)
            logging.info(f"WhatsApp sent to {phone} (Template: {template_name})")
            return True

        except Exception as e:
            logging.error(f"Failed to send WhatsApp to {phone}: {e}")
            return False



