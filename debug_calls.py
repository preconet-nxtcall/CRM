
from app import create_app, db
from app.models import CallHistory
from datetime import datetime, timedelta

app = create_app()

with app.app_context():
    print("--- DEBUG CALL HISTORY ---")
    now_utc = datetime.utcnow()
    print(f"Current UTC: {now_utc}")
    
    # Get all calls from last 24 hours
    since = now_utc - timedelta(days=2)
    calls = CallHistory.query.filter(CallHistory.timestamp >= since).order_by(CallHistory.timestamp.desc()).all()
    
    print(f"Found {len(calls)} calls in last 48h")
    
    ist_delta = timedelta(hours=5, minutes=30)
    
    for c in calls[:20]:
        utc_ts = c.timestamp
        ist_ts = utc_ts + ist_delta
        print(f"ID: {c.id} | UTC: {utc_ts} | IST: {ist_ts} | Date: {ist_ts.date()}")
