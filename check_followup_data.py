from app import create_app
from app.models import db, Followup, User

app = create_app()

with app.app_context():
    count = Followup.query.count()
    print(f"Total Followups: {count}")
    
    if count > 0:
        latest = Followup.query.order_by(Followup.created_at.desc()).limit(5).all()
        for f in latest:
            user = User.query.get(f.user_id)
            user_name = user.name if user else "UNKNOWN_USER"
            print(f"ID: {f.id} | User: {f.user_id} ({user_name}) | Time: {f.date_time} | Created: {f.created_at}")

    # Check Users
    user_count = User.query.count()
    print(f"Total Users: {user_count}")
