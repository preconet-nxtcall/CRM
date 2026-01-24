from app import create_app
from app.models import db, FacebookConnection, Lead, Admin

app = create_app()

with app.app_context():
    print("--- CHECKING FACEBOOK CONNECTIONS ---")
    connections = FacebookConnection.query.all()
    if not connections:
        print("No Facebook Connections found in DB.")
    else:
        for conn in connections:
            admin = Admin.query.get(conn.admin_id)
            admin_name = admin.name if admin else "Unknown"
            print(f"Admin: {admin_name} (ID: {conn.admin_id})")
            print(f"  Page ID: {conn.page_id}")
            print(f"  Page Name: {conn.page_name}")
            print(f"  Status: {conn.status}")
            print(f"  Updated At: {conn.updated_at}")
            print("-" * 20)

    print("\n--- CHECKING RECENT LEADS ---")
    leads = Lead.query.order_by(Lead.created_at.desc()).limit(5).all()
    if not leads:
        print("No leads found in DB.")
    else:
        for lead in leads:
            print(f"Lead ID: {lead.id} | Source: {lead.source}")
            print(f"  Name: {lead.name} | Phone: {lead.phone}")
            print(f"  FB Lead ID: {lead.facebook_lead_id}")
            print(f"  Created At: {lead.created_at}")
            print("-" * 20)
