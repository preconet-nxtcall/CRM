from app import create_app
from app.models import db, Followup
from datetime import timedelta

def revert_migration():
    app = create_app()
    with app.app_context():
        print("🔄 Reverting timezone migration (IST -> UTC)...")
        
        # Filter for records created BEFORE the migration logic was applied
        # Approx timestamp: 2025-12-24 07:40:00 UTC (Current time is ~07:50 UTC)
        cutoff = "2025-12-24 07:40:00" 
        followups = Followup.query.filter(Followup.created_at < cutoff).all()
        
        # IST offset to SUBTRACT
        ist_offset = timedelta(hours=5, minutes=30)
        
        updated = 0
        for followup in followups:
            try:
                # Convert back from IST to UTC
                if followup.date_time:
                    followup.date_time = followup.date_time - ist_offset
                
                if followup.created_at:
                    followup.created_at = followup.created_at - ist_offset
                    
                if followup.updated_at:
                    followup.updated_at = followup.updated_at - ist_offset
                    
                updated += 1
            except Exception as e:
                print(f"Error reverting #{followup.id}: {e}")
                
        try:
            db.session.commit()
            print(f"✅ Successfully reverted {updated} records.")
        except Exception as e:
            db.session.rollback()
            print(f"Error committing: {e}")

if __name__ == "__main__":
    revert_migration()
