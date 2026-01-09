#!/usr/bin/env bash
set -e

echo "🚀 Starting build process..."

# Install dependencies
echo "⬇️ Installing dependencies..."
pip install -r requirements.txt

# Initialize database
echo "👤 Initializing database and SuperAdmin..."
python3 - <<'PYCODE'
from app import create_app
from app.models import db, SuperAdmin
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    # Only creating tables if they don't exist
    db.create_all()
    print("✅ Tables ensured")

    if not SuperAdmin.query.first():
        admin = SuperAdmin(
            name="Super Admin",
            email="nxtcall.app@gmail.com"
        )
        admin.set_password("kolkata@2025")
        db.session.add(admin)
        db.session.commit()
        print("✅ Default Super Admin created")
    else:
        print("ℹ️ Super Admin already exists, skipping")
PYCODE

# Run DB fix scripts if needed
echo "🔧 Running database fix scripts..."
python3 db_fix_constraints.py || echo "⚠️ db_fix_constraints.py failed, but continuing..."
python3 fix_timezone_migration.py || echo "⚠️ fix_timezone_migration.py failed, but continuing..."

# Force Reset Super Admin (Added for Free Tier Shell limitation)
echo "🔑 Resetting Super Admin credentials..."
python3 reset_super_admin.py

echo "✅ Build completed successfully!"
