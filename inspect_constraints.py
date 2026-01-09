
from app import create_app
from app.models import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        # Get unique constraints on users table
        sql = text("SELECT conname FROM pg_constraint WHERE conrelid = 'users'::regclass AND contype = 'u'")
        results = db.session.execute(sql).fetchall()
        print("CONSTRAINTS:", [r[0] for r in results])
    except Exception as e:
        print(f"Error: {e}")
