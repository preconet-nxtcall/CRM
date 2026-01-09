#!/usr/bin/env python
"""
Database migration script to convert existing follow-up reminders from UTC to IST (UTC+5:30)
This script should be run ONCE on the server after deploying the timezone fix.
"""

from app import create_app
from app.models import db, Followup
from datetime import timedelta

def migrate_followup_timezones():
    app = create_app()
    with app.app_context():
        print("🔄 Starting timezone migration for follow-up reminders...")
        
        # Get all followups
        followups = Followup.query.all()
        total = len(followups)
        
        if total == 0:
            print("ℹ️  No follow-ups found in database.")
            return
        
        print(f"📋 Found {total} follow-up reminder(s) to migrate.")
        
        # IST offset: UTC+5:30
        ist_offset = timedelta(hours=5, minutes=30)
        
        updated = 0
        for followup in followups:
            try:
                # Convert date_time from UTC to IST
                if followup.date_time:
                    old_time = followup.date_time
                    followup.date_time = followup.date_time + ist_offset
                    print(f"  ✓ Reminder #{followup.id}: {old_time} → {followup.date_time}")
                
                # Convert created_at from UTC to IST
                if followup.created_at:
                    followup.created_at = followup.created_at + ist_offset
                
                # Convert updated_at from UTC to IST if it exists
                if followup.updated_at:
                    followup.updated_at = followup.updated_at + ist_offset
                
                updated += 1
            except Exception as e:
                print(f"  ⚠️  Error updating reminder #{followup.id}: {e}")
        
        # Commit all changes
        try:
            db.session.commit()
            print(f"\n✅ Successfully migrated {updated}/{total} reminder(s) from UTC to IST (+5:30)")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error committing changes: {e}")
            raise

if __name__ == "__main__":
    migrate_followup_timezones()
