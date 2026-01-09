from app import create_app
from app.models import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("Checking for recording_path column in call_history...")
    try:
        # Check if column exists
        inspector = db.inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('call_history')]
        
        if 'recording_path' not in columns:
            print("Adding recording_path column...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE call_history ADD COLUMN recording_path VARCHAR(1024)"))
                conn.commit()
            print("Column added successfully.")
        else:
            print("Column recording_path already exists.")
            
    except Exception as e:
        print(f"Error: {e}")
