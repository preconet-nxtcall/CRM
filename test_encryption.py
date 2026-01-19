from app import create_app, db
from app.models import IndiamartSettings

app = create_app()

with app.app_context():
    print("🔐 Verifying Encryption...")
    
    # 1. Create a dummy setting
    s = IndiamartSettings(admin_id=99999, mobile_number="9999999999")
    original_key = "MY_SECRET_KEY_123"
    
    print(f"   Original Key: {original_key}")
    s.set_api_key(original_key)
    
    # 2. Check internal storage (should be encrypted)
    print(f"   Stored (Encrypted): {s.api_key}")
    
    if s.api_key == original_key:
        print("   ❌ FAIL: Key is stored in plain text!")
    elif "gAAAA" in s.api_key: # Fernet tokens usually start with gAAAA
        print("   ✅ PASS: Key appears encrypted.")
    else:
         print(f"   ⚠️ Key is changed but format unknown: {s.api_key}")

    # 3. Check decryption
    decrypted = s.get_api_key()
    print(f"   Decrypted: {decrypted}")
    
    if decrypted == original_key:
         print("   ✅ PASS: Decryption successful.")
    else:
         print("   ❌ FAIL: Decryption mismatch.")
