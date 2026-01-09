"""
Database migration script to create activity_logs table if it doesn't exist
"""
from app import create_app
from app.models import db

def create_activity_logs_table():
    app = create_app()
    with app.app_context():
        # Create table using raw SQL to ensure it exists
        db.session.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_role VARCHAR(20) NOT NULL,
                actor_id INTEGER NOT NULL,
                action VARCHAR(255) NOT NULL,
                target_type VARCHAR(50) NOT NULL,
                target_id INTEGER,
                extra_data TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.session.commit()
        print("✓ activity_logs table created/verified successfully")

if __name__ == "__main__":
    create_activity_logs_table()
