
import os
from app import create_app

app = create_app()

print("="*60)
print("🔍 DEBUG FILE PATHS")
print("="*60)

with app.app_context():
    print(f"📂 Current Working Directory (os.getcwd): {os.getcwd()}")
    print(f"📂 Flask App Root Path (app.root_path): {app.root_path}")
    
    # Check 1: Static Uploads (Where we THINK they go)
    static_uploads = os.path.join(app.root_path, 'static', 'uploads')
    print(f"\n👉 Checking Static Uploads: {static_uploads}")
    if os.path.exists(static_uploads):
        print("   ✅ Directory EXISTS")
        for root, dirs, files in os.walk(static_uploads):
             for f in files:
                 print(f"      📄 {os.path.join(root, f)}")
    else:
        print("   ❌ Directory NOT FOUND")

    # Check 2: Root Uploads (Legacy)
    root_uploads = os.path.join(os.getcwd(), 'uploads')
    print(f"\n👉 Checking Root Uploads: {root_uploads}")
    if os.path.exists(root_uploads):
        print("   ✅ Directory EXISTS")
        for root, dirs, files in os.walk(root_uploads):
             for f in files:
                 print(f"      📄 {os.path.join(root, f)}")
    else:
        print("   ❌ Directory NOT FOUND")

    # Check 3: Check where 'recordings' went if anywhere else
    print("\n👉 Checking for 'recordings' folder anywhere in backend...")
    for root, dirs, files in os.walk(os.getcwd()):
        if 'recordings' in dirs:
            found_path = os.path.join(root, 'recordings')
            print(f"   💡 Found 'recordings' at: {found_path}")
            # List files there
            for r, d, f in os.walk(found_path):
                for file in f:
                     print(f"      📄 {os.path.join(r, file)}")
