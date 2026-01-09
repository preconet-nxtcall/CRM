
from app import create_app, db
from app.models import CallHistory
import os

app = create_app()

with app.app_context():
    print("--- Checking Recent Call History Recordings ---")
    # Get last 10 records with a recording_path
    records = CallHistory.query.filter(CallHistory.recording_path != None).order_by(CallHistory.timestamp.desc()).limit(10).all()
    
    for r in records:
        print(f"ID: {r.id} | User: {r.user_id} | Path: {r.recording_path}")
        
    print("\n--- Checking File System for 'recordings' ---")
    base_upload_path = os.path.join(app.root_path, 'static', 'uploads', 'recordings')
    if os.path.exists(base_upload_path):
        for root, dirs, files in os.walk(base_upload_path):
            for file in files:
                print(os.path.join(root, file))
    else:
        print(f"Path not found: {base_upload_path}")
