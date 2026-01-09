import sqlite3
import os
from app import create_app, db
from sqlalchemy import text

app = create_app()

def fix_schema():
    with app.app_context():
        print("Checking database schema...")
        engine = db.engine
        inspector = db.inspect(engine)
        columns = [c['name'] for c in inspector.get_columns('attendances')]
        
        print(f"Current columns in 'attendances': {columns}")
        
        # Columns to add
        new_columns = {
            'check_out_latitude': 'FLOAT',
            'check_out_longitude': 'FLOAT',
            'check_out_address': 'VARCHAR(500)',
            'check_out_image': 'VARCHAR(1024)'
        }
        
        with engine.connect() as conn:
            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    print(f"Adding missing column: {col_name} ({col_type})")
                    try:
                        # SQLite syntax (assuming SQLite for local dev, but works for most)
                        # If Postgres, we might need 'COLUMN' keyword, but typically acceptable.
                        # Using text() for safety.
                        conn.execute(text(f'ALTER TABLE attendances ADD COLUMN {col_name} {col_type}'))
                        print(f"✅ Added {col_name}")
                    except Exception as e:
                        print(f"❌ Failed to add {col_name}: {e}")
                else:
                    print(f"Skipping {col_name} (already exists)")
            
            conn.commit()
            print("Schema update check complete.")

if __name__ == "__main__":
    fix_schema()
