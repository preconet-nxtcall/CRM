from app import create_app
from app.models import db, SuperAdmin

app = create_app()

with app.app_context():
    print("🔄 resetting Super Admin password...")
    
    admin = SuperAdmin.query.filter_by(email="nxtcall.app@gmail.com").first()
    
    if not admin:
        print("⚠️ Super Admin not found by email. Checking first record...")
        admin = SuperAdmin.query.first()
        if admin:
             print(f"⚠️ Found existing Super Admin with different email: {admin.email}. Updating to nxtcall.app@gmail.com...")
             admin.email = "nxtcall.app@gmail.com"
             admin.name = "Super Admin"
        
    if not admin:
        print("❌ No Super Admin found at all. Creating one...")
        admin = SuperAdmin(
            name="Super Admin",
            email="nxtcall.app@gmail.com"
        )
        db.session.add(admin)
    
    # FORCE RESET PASSWORD
    new_password = "kolkata@2025"
    admin.set_password(new_password)
    db.session.commit()
    
    print(f"✅ Super Admin password reset successfully!")
    print(f"📧 Email: {admin.email}")
    print(f"🔑 Password: {new_password}")
