
from app import create_app
from app.models import db, CallHistory, User, Admin
from sqlalchemy import func
from datetime import datetime, timedelta

app = create_app()

with app.app_context():
    # 1. Check if there are ANY calls
    total_calls = CallHistory.query.count()
    print(f"Total Calls: {total_calls}")

    # 2. Check latest call
    latest_call = CallHistory.query.order_by(CallHistory.timestamp.desc()).first()
    if latest_call:
        print(f"Latest Call Timestamp: {latest_call.timestamp} (Type: {type(latest_call.timestamp)})")
    
    # 3. Simulate the dashboard query
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    # Get first admin id (assuming user is admin)
    # We can try to guess admin or just query all calls for now to see if grouping works
    
    print(f"Querying for calls since: {week_ago}")

    try:
        trend_rows = (
            db.session.query(
                func.date(CallHistory.timestamp).label("date"),
                func.count(CallHistory.id).label("count")
            )
            .filter(CallHistory.timestamp >= week_ago)
            .group_by(func.date(CallHistory.timestamp))
            .all()
        )
        print("SQL Grouping Results:")
        for r in trend_rows:
            print(f"Date: {r.date}, Count: {r.count}")
    except Exception as e:
        print(f"SQL Verification Failed: {e}")

    # 4. Alternative Python Grouping
    print("\nAlternative Python Grouping Check:")
    raw_calls = CallHistory.query.filter(CallHistory.timestamp >= week_ago).all()
    counts = {}
    for c in raw_calls:
        d_str = str(c.timestamp.date())
        counts[d_str] = counts.get(d_str, 0) + 1
    
    for d, c in counts.items():
        print(f"Date: {d}, Count: {c}")
