"""
Script to verify and create activity_logs table in production database
Run this on your production server to ensure the table exists
"""
from app import create_app
from app.models import db, ActivityLog
from sqlalchemy import inspect

def setup_activity_logs_table():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        
        # Check if table exists
        if 'activity_logs' in inspector.get_table_names():
            print("✓ activity_logs table already exists")
            
            # Check row count
            count = db.session.query(ActivityLog).count()
            print(f"✓ Current log entries: {count}")
            
            # Show recent logs
            if count > 0:
                recent = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(5).all()
                print("\nRecent activity logs:")
                for log in recent:
                    print(f"  - {log.action} (by {log.actor_role.value} #{log.actor_id}) at {log.timestamp}")
        else:
            print("✗ activity_logs table does NOT exist")
            print("Creating table using db.create_all()...")
            
            # Create all tables (safe - won't drop existing tables)
            db.create_all()
            
            print("✓ activity_logs table created successfully")
            print("You can now perform admin actions and they will be logged")

if __name__ == "__main__":
    setup_activity_logs_table()
