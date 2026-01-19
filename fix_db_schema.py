from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("🔧 Fixing Lead Table for SaaS Multi-Tenancy...")
    
    with db.engine.connect() as conn:
        try:
            # 1. Drop the old global unique index on facebook_lead_id if it exists
            print("   - Dropping old unique index on facebook_lead_id...")
            try:
                # The default index name usually created by SQLAlchemy for unique=True
                # postgres naming convention: ix_leads_facebook_lead_id or leads_facebook_lead_id_key
                # Let's try to drop the constraint directly
                conn.execute(text("ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_facebook_lead_id_key;"))
                # Also drop index if it exists separately
                conn.execute(text("DROP INDEX IF EXISTS ix_leads_facebook_lead_id;"))
            except Exception as e:
                print(f"     (Info) Drop index failed or not needed: {e}")

        except Exception as e:
            print(f"❌ Error during modification: {e}")
            
        # 2. Add the new composite unique constraint
        try:
            print("   - Adding new composite unique constraint (admin_id, facebook_lead_id)...")
            # This ensures (admin 1, lead 123) and (admin 2, lead 123) can both exist
            conn.execute(text("ALTER TABLE leads ADD CONSTRAINT _admin_lead_uc UNIQUE (admin_id, facebook_lead_id);"))
            print("   ✅ Success: Constraints updated.")
        except Exception as e:
            if "already exists" in str(e):
                 print("   ✅ Constraint already exists.")
            else:
                 print(f"   ❌ Error adding constraint: {e}")

        conn.commit()
    
    print("🎉 Database Schema Updated for SaaS!")
