from app import create_app
from app.models import Admin, User
from datetime import datetime

app = create_app()

with app.app_context():
    admins = Admin.query.all()
    print(f"--- Checking {len(admins)} Admins ---")
    today = datetime.utcnow().date()
    print(f"UTC Date: {today}")
    
    for admin in admins:
        exp_status = "ACTIVE"
        if admin.expiry_date:
            exp_date = admin.expiry_date.date() if isinstance(admin.expiry_date, datetime) else admin.expiry_date
            if exp_date < today:
                exp_status = "EXPIRED"
            days_left = (exp_date - today).days
        else:
            exp_date = "None (Lifetime)"
            days_left = "N/A"

        print(f"ID: {admin.id} | Name: {admin.name} | Expiry: {exp_date} | Status: {exp_status} | Days Left: {days_left}")

    print("\n--- Checking Users (Agents) ---")
    users = User.query.all()
    for user in users:
        u_exp = "None"
        u_status = "OK"
        if user.subscription_expiry_date:
            u_date = user.subscription_expiry_date.date() if isinstance(user.subscription_expiry_date, datetime) else user.subscription_expiry_date
            u_exp = str(u_date)
            if u_date < today:
                u_status = "EXPIRED (BLOCKING)"
        
        print(f"User ID: {user.id} | Name: {user.name} | Role: Support/Agent | User Expiry: {u_exp} | Status: {u_status}")
