import os
import base64
from cryptography.fernet import Fernet
from flask import current_app

def _get_fernet_key():
    """
    Generates a valid Fernet key from the app's SECRET_KEY.
    Fernet requires a 32-byte url-safe base64-encoded key.
    """
    secret = current_app.config.get('SECRET_KEY', 'default-dev-secret-key-change-in-prod')
    # Pad or truncate to 32 bytes for the key generation basic mechanism
    # A robust way is to hash it and encode
    import hashlib
    key = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key)

def encrypt_value(value):
    """
    Encrypts a string value. Returns the encrypted hash string.
    """
    if not value:
        return None
    try:
        f = Fernet(_get_fernet_key())
        return f.encrypt(value.encode()).decode()
    except Exception as e:
        current_app.logger.error(f"Encryption failed: {e}")
        raise e

def decrypt_value(token):
    """
    Decrypts an encrypted token string back to the original value.
    """
    if not token:
        return None
    try:
        f = Fernet(_get_fernet_key())
        return f.decrypt(token.encode()).decode()
    except Exception as e:
        current_app.logger.error(f"Decryption failed: {e}")
        return None
