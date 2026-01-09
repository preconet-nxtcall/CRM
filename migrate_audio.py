from app import create_app, db
from app.models import CallHistory
import os
import sys
from pydub import AudioSegment

def migrate_audio():
    app = create_app()
    
    with app.app_context():
        print("🎵 Starting Audio Migration...")
        
        # 1. Find all records with .amr or .3gp
        # Logic: Filter strings ending with .amr or .3gp
        # SQLAlchemy 'endswith'
        records = CallHistory.query.filter(
            (CallHistory.recording_path.ilike('%.amr')) | 
            (CallHistory.recording_path.ilike('%.3gp'))
        ).all()
        
        print(f"📋 Found {len(records)} legacy recordings to process.")
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for record in records:
            try:
                # Construct full path
                # Path stored in DB is relative: "uploads/recordings/user_X/filename.amr"
                # Actual location: backend/app/static/uploads/...
                
                # Check where it lives
                relative_path = record.recording_path
                if not relative_path:
                    continue
                    
                full_path_static = os.path.join(app.root_path, 'static', relative_path)
                full_path_root = os.path.join(os.getcwd(), relative_path)
                
                source_path = None
                if os.path.exists(full_path_static):
                    source_path = full_path_static
                elif os.path.exists(full_path_root):
                    source_path = full_path_root
                
                if not source_path:
                    print(f"⚠️ File missing for ID {record.id}: {relative_path}")
                    skipped_count += 1
                    continue
                
                # Convert
                print(f"🔄 Converting: {os.path.basename(source_path)}")
                
                fmt = 'amr' if source_path.lower().endswith('.amr') else '3gp'
                audio = AudioSegment.from_file(source_path, format=fmt)
                
                # New Path
                new_filename = os.path.splitext(os.path.basename(source_path))[0] + ".mp3"
                dirname = os.path.dirname(source_path)
                new_full_path = os.path.join(dirname, new_filename)
                
                audio.export(new_full_path, format="mp3")
                
                if os.path.exists(new_full_path):
                    # Update DB
                    # We keep the directory part of the relative path, just change extension
                    new_relative_path = os.path.splitext(relative_path)[0] + ".mp3"
                    record.recording_path = new_relative_path
                    success_count += 1
                    print(f"   ✅ Done: {new_filename}")
                else:
                    print(f"   ❌ Export failed")
                    error_count += 1
            
            except Exception as e:
                print(f"   ❌ Error converting ID {record.id}: {e}")
                error_count += 1
        
        db.session.commit()
        print("\n========================================")
        print(f"🎉 Migration Complete")
        print(f"✅ Converted: {success_count}")
        print(f"❌ Errors:    {error_count}")
        print(f"⏩ Skipped:   {skipped_count}")
        print("========================================")

if __name__ == "__main__":
    migrate_audio()
