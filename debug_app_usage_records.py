
from app import create_app, db
from app.models import AppUsage

app = create_app()

with app.app_context():
    records = AppUsage.query.order_by(AppUsage.id.desc()).limit(5).all()
    print(f"Found {len(records)} records")
    for r in records:
        print(f"ID: {r.id}, Start: {r.start_time}, End: {r.end_time}, Created: {r.created_at}")
