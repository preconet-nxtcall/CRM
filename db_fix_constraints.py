import os
from app import create_app
from app.models import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("🔧 Applying database fixes...")
    
    # 1. Add unique constraint to CallHistory
    # We use a raw SQL command because SQLAlchemy model changes need migration scripts
    try:
        # Check if constraint exists (PostgreSQL specific)
        check_sql = text("""
            SELECT count(*) 
            FROM pg_constraint 
            WHERE conname = 'uq_call_history_dedup'
        """)
        result = db.session.execute(check_sql).scalar()
        
        if result == 0:
            print("Adding unique constraint to call_history...")
            # First, delete duplicates if any (keep the one with max ID)
            # This is complex, so we might skip deletion and just add constraint with 'SKIP LOCKED' or similar if supported, 
            # but standard SQL doesn't support that easily.
            # For now, we'll try to add the constraint. If it fails due to duplicates, we'll print a warning.
            
            sql = text("""
                ALTER TABLE call_history 
                ADD CONSTRAINT uq_call_history_dedup 
                UNIQUE (user_id, timestamp, phone_number, call_type, duration);
            """)
            db.session.execute(sql)
            db.session.commit()
            print("✅ Unique constraint added to call_history.")
        else:
            print("ℹ️ Unique constraint 'uq_call_history_dedup' already exists.")
            
    except Exception as e:
        db.session.rollback()
        print(f"⚠️ Could not add constraint to call_history (likely duplicates exist): {e}")

    # 2. Add unique constraint to Attendance
    try:
        check_sql = text("""
            SELECT count(*) 
            FROM pg_constraint 
            WHERE conname = 'uq_attendance_external_id'
        """)
        result = db.session.execute(check_sql).scalar()
        
        if result == 0:
            print("Adding unique constraint to attendance...")
            sql = text("""
                ALTER TABLE attendances 
                ADD CONSTRAINT uq_attendance_external_id 
                UNIQUE (user_id, external_id);
            """)
            db.session.execute(sql)
            db.session.commit()
            print("✅ Unique constraint added to attendances.")
        else:
            print("ℹ️ Unique constraint 'uq_attendance_external_id' already exists.")
            
    except Exception as e:
        db.session.rollback()
        print(f"⚠️ Could not add constraint to attendances: {e}")

    # 3. Add missing 'extra_data' column to activity_logs
    try:
        # Check if column exists
        check_col_sql = text("""
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_name='activity_logs' AND column_name='extra_data'
        """)
        result = db.session.execute(check_col_sql).scalar()

        if result == 0:
            print("Adding missing column 'extra_data' to activity_logs...")
            sql = text("ALTER TABLE activity_logs ADD COLUMN extra_data TEXT")
            db.session.execute(sql)
            db.session.commit()
            print("✅ Column 'extra_data' added to activity_logs.")
        else:
            print("ℹ️ Column 'extra_data' already exists in activity_logs.")

    except Exception as e:
        db.session.rollback()
        print(f"⚠️ Could not add column to activity_logs: {e}")

    print("🏁 Database fixes completed.")
