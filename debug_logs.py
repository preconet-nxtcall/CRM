from app import create_app
from app.models import db, ActivityLog

app = create_app()

with app.app_context():
    print("--- Latest 20 Activity Logs ---")
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all()
    for log in logs:
        print(f"ID: {log.id} | Action: '{log.action}' | Target Type: '{log.target_type}' | Target ID: {log.target_id}")

    print("\n--- Checking for 'admin' target_type ---")
    admin_logs = ActivityLog.query.filter_by(target_type='admin').limit(10).all()
    for log in admin_logs:
        print(f"ID: {log.id} | Action: '{log.action}'")
