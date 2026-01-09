from app import create_app
from app.models import db, CallHistory
from sqlalchemy import func

app = create_app()

with app.app_context():
    print("--- Checking CallHistory Data ---")
    
    # Check total count
    total = CallHistory.query.count()
    print(f"Total records: {total}")
    
    # Check records for Nov 20, 2025
    date_20 = '2025-11-20'
    count_20 = CallHistory.query.filter(func.date(CallHistory.timestamp) == date_20).count()
    print(f"Records for {date_20}: {count_20}")
    
    # Check records for Nov 23, 2025
    date_23 = '2025-11-23'
    count_23 = CallHistory.query.filter(func.date(CallHistory.timestamp) == date_23).count()
    print(f"Records for {date_23}: {count_23}")
    
    # List last 10 records timestamps
    print("\n--- Last 10 Records ---")
    last_10 = CallHistory.query.order_by(CallHistory.timestamp.desc()).limit(10).all()
    for c in last_10:
        print(f"ID: {c.id}, Timestamp: {c.timestamp}")
