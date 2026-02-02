from app import create_app, db
from app.models import LeadStatusHistory

app = create_app()

with app.app_context():
    try:
        LeadStatusHistory.__table__.create(db.engine)
        print("Table 'lead_status_history' created successfully.")
    except Exception as e:
        print(f"Error (table might exist): {e}")
