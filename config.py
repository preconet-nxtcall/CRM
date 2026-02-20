import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://")
    
    # Connection Pooling for High Concurrency (100k users ready)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 20,
        "max_overflow": 40,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-secret-key")
    
    # Notification Config
    ZEPTOMAIL_USER = os.environ.get("ZEPTOMAIL_USER", "")
    ZEPTOMAIL_API_TOKEN = os.environ.get("ZEPTOMAIL_API_TOKEN", "")

    # Facebook Integration
    FACEBOOK_VERIFY_TOKEN = os.environ.get("FACEBOOK_VERIFY_TOKEN", "nxtcall_fb_webhook_2026")
    FACEBOOK_APP_ID = os.environ.get("FACEBOOK_APP_ID", "1537220340728257")
    FACEBOOK_APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET", "774f3a44a2590515de08680001d7bbaf")

    # Wasabi / S3 Storage
    WASABI_ACCESS_KEY = os.environ.get("WASABI_ACCESS_KEY", "")
    WASABI_SECRET_KEY = os.environ.get("WASABI_SECRET_KEY", "")
    WASABI_REGION = os.environ.get("WASABI_REGION", "us-east-1")
    WASABI_BUCKET_NAME = os.environ.get("WASABI_BUCKET_NAME", "")
    WASABI_ENDPOINT_URL = os.environ.get("WASABI_ENDPOINT_URL", "https://s3.wasabisys.com")


