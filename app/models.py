# app/models.py
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import enum
import json
import uuid
from sqlalchemy.types import Text, TypeDecorator
from sqlalchemy import JSON as SA_JSON

db = SQLAlchemy()
bcrypt = Bcrypt()

# -------------------------
# Helper functions
# -------------------------
def now():
    return datetime.utcnow()

def gen_uuid():
    return uuid.uuid4().hex


# =========================================================
# ENUM: User Roles
# =========================================================
class UserRole(enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"


# =========================================================
# JSON Type Fallback
# =========================================================
class JSONType(TypeDecorator):
    impl = Text

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        try:
            return json.dumps(value)
        except:
            return json.dumps(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return json.loads(value)
        except:
            return value

def JSONAuto():
    try:
        return SA_JSON
    except:
        return JSONType


# =========================================================
# SUPER ADMIN
# =========================================================
class SuperAdmin(db.Model):
    __tablename__ = "super_admins"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=now)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


# =========================================================
# ADMIN (Company Account)
# =========================================================
class Admin(db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    user_limit = db.Column(db.Integer, default=10)

    # Keep expiry as DateTime (NOT date)
    expiry_date = db.Column(db.DateTime, nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey("super_admins.id"), nullable=True)
    creator = db.relationship("SuperAdmin")

    created_at = db.Column(db.DateTime, default=now)
    last_login = db.Column(db.DateTime)
    
    # Session Management
    current_session_id = db.Column(db.String(100), nullable=True)

    is_active = db.Column(db.Boolean, default=True)

    users = db.relationship(
        "User",
        backref="admin",
        lazy=True,
        cascade="all, delete-orphan"
    )
    
    # Relationships for Facebook
    facebook_pages = db.relationship("FacebookPage", backref="admin", lazy=True, cascade="all, delete-orphan")
    leads = db.relationship("Lead", backref="admin", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def is_expired(self):
        """
        SAFE EXPIRY CHECK ✔ FIXED
        Always compare datetime objects.
        """
        if not self.expiry_date:
            return False

        return datetime.utcnow() > self.expiry_date


# =========================================================
# USER (Agent)
# =========================================================
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False) # Removed unique=True (Global uniqueness not required)
    password_hash = db.Column(db.String(255), nullable=False)

    phone = db.Column(db.String(20))
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False)

    is_active = db.Column(db.Boolean, default=True)
    performance_score = db.Column(db.Float, default=0.0)

    created_at = db.Column(db.DateTime, default=now)
    last_login = db.Column(db.DateTime)
    last_sync = db.Column(db.DateTime)
    
    # Status & Suspension
    status = db.Column(db.String(20), default='active')  # active, blocked
    is_suspended = db.Column(db.Boolean, default=False)
    subscription_expiry_date = db.Column(db.DateTime, nullable=True)

    # Session Management
    current_session_id = db.Column(db.String(100), nullable=True)
    fcm_token = db.Column(db.String(255), nullable=True) # For Notifications

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def update_sync_time(self):
        self.last_sync = datetime.utcnow()

    def get_sync_summary(self):
        from app.models import CallHistory, Attendance
        return {
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "call_records": CallHistory.query.filter_by(user_id=self.id).count(),
            "attendance_records": Attendance.query.filter_by(user_id=self.id).count(),
        }


# =========================================================
# ATTENDANCE
# =========================================================
class Attendance(db.Model):
    __tablename__ = "attendances"

    id = db.Column(db.String(64), primary_key=True, default=gen_uuid)
    external_id = db.Column(db.String(64), index=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    check_in = db.Column(db.DateTime, nullable=False)
    check_out = db.Column(db.DateTime)

    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    address = db.Column(db.String(500))

    check_out_latitude = db.Column(db.Float)
    check_out_longitude = db.Column(db.Float)
    check_out_address = db.Column(db.String(500))

    image_path = db.Column(db.String(1024))
    check_out_image = db.Column(db.String(1024))
    
    status = db.Column(db.String(50), default="present", index=True)

    synced = db.Column(db.Boolean, default=False)
    sync_timestamp = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=now)

    user = db.relationship("User", backref=db.backref("attendance_records", lazy="dynamic", cascade="all, delete-orphan", passive_deletes=True))

    def to_dict(self):
        return {
            "id": self.id,
            "external_id": self.external_id,
            "user_id": self.user_id,
            "check_in": self.check_in.isoformat() if self.check_in else None,
            "check_out": self.check_out.isoformat() if self.check_out else None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": self.address,
            "image_path": self.image_path,
            "status": self.status,
            "synced": self.synced,
            "sync_timestamp": self.sync_timestamp.isoformat() if self.sync_timestamp else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =========================================================
# CALL HISTORY
# =========================================================
class CallHistory(db.Model):
    __tablename__ = "call_history"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    phone_number = db.Column(db.String(50))
    formatted_number = db.Column(db.String(100))
    call_type = db.Column(db.String(20))  # incoming/outgoing/missed/rejected

    timestamp = db.Column(db.DateTime)
    duration = db.Column(db.Integer)
    contact_name = db.Column(db.String(150))
    recording_path = db.Column(db.String(1024), nullable=True)

    created_at = db.Column(db.DateTime, default=now, index=True)

    # Indexes for frequent filtering/searching
    __table_args__ = (
        db.Index('idx_call_history_timestamp', 'timestamp'),
        db.Index('idx_call_history_phone', 'phone_number'),
        db.Index('idx_call_history_call_type', 'call_type'),
    )

    user = db.relationship("User", backref=db.backref("call_history_records", lazy="dynamic", cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "phone_number": self.phone_number,
            "formatted_number": self.formatted_number,
            "call_type": self.call_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "duration": self.duration,
            "contact_name": self.contact_name,
            "recording_path": self.recording_path,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =========================================================
# CALL METRICS
# =========================================================
class CallMetrics(db.Model):
    __tablename__ = "call_metrics"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    total_calls = db.Column(db.Integer, default=0)
    incoming_calls = db.Column(db.Integer, default=0)
    outgoing_calls = db.Column(db.Integer, default=0)
    missed_calls = db.Column(db.Integer, default=0)
    rejected_calls = db.Column(db.Integer, default=0)

    total_duration = db.Column(db.Integer, default=0)
    period_days = db.Column(db.Integer, default=0)

    sync_timestamp = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now)


# =========================================================
# ACTIVITY LOG
# =========================================================
class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)

    actor_role = db.Column(db.Enum(UserRole), nullable=False)
    actor_id = db.Column(db.Integer, nullable=False)

    action = db.Column(db.String(255), nullable=False)

    target_type = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.Integer)

    extra_data = db.Column(JSONAuto())
    timestamp = db.Column(db.DateTime, default=now)


# =========================================================
# APP USAGE MODEL
# =========================================================
class AppUsage(db.Model):
    __tablename__ = "app_usage"

    id = db.Column(db.Integer, primary_key=True)
    
    # Links
    attendance_id = db.Column(db.String(64), db.ForeignKey("attendances.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    # Metadata
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False)
    total_usage_seconds = db.Column(db.Integer, default=0)
    
    # Detailed Data (JSON)
    # List of {package_name, app_name, usage_seconds}
    apps_data = db.Column(JSONAuto())
    
    created_at = db.Column(db.DateTime, default=now)

    # Relationships
    attendance = db.relationship("Attendance", backref=db.backref("app_usage_records", cascade="all, delete-orphan"))
    user = db.relationship("User", backref="app_usages")

    def to_dict(self):
        return {
            "id": self.id,
            "attendance_id": self.attendance_id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else "Unknown",
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_usage_seconds": self.total_usage_seconds,
            "apps_data": self.apps_data,
            "created_at": self.created_at.isoformat()
        }


# =========================================================
# FOLLOWUP MODEL
# =========================================================
class Followup(db.Model):
    __tablename__ = "followups"

    id = db.Column(db.String(100), primary_key=True) # UUID from app
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    contact_name = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=True)
    
    date_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False) # pending, completed, cancelled
    
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)
    
    # Relationships
    user = db.relationship("User", backref=db.backref("followups", cascade="all, delete-orphan", passive_deletes=True))

    def to_dict(self):
        return {
            "reminder_id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else "Unknown",
            "contact_name": self.contact_name,
            "phone": self.phone,
            "message": self.message,
            "date_time": self.date_time.isoformat() if self.date_time else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =========================================================
# PASSWORD RESET MODEL
# =========================================================
class PasswordReset(db.Model):
    __tablename__ = "password_resets"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), nullable=False, index=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now)

    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at


# =========================================================
# FREE TRIAL MODEL
# =========================================================
class FreeTrial(db.Model):
    __tablename__ = "free_trials"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    work_email = db.Column(db.String(150), nullable=False)
    company_name = db.Column(db.String(150), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    
    created_at = db.Column(db.DateTime, default=now)
    status = db.Column(db.String(20), default="active") # active, blocked

    def to_dict(self):
        # Calculate status mainly for display if not blocked
        display_status = self.status
        if self.status == "active":
             # Check if expired ( > 15 days)
             if self.created_at and datetime.utcnow() > self.created_at + timedelta(days=15):
                 display_status = "expired"

        return {
            "id": self.id,
            "name": self.name,
            "work_email": self.work_email,
            "company_name": self.company_name,
            "phone_number": self.phone_number,
            "created_at": (self.created_at.isoformat() + 'Z') if self.created_at else None,
            "status": display_status,
            "is_blocked": self.status == "blocked"
        }


# =========================================================
# FACEBOOK CONNECTION (Strict SaaS Infrastructure)
# =========================================================
class FacebookConnection(db.Model):
    __tablename__ = "facebook_connections"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, unique=True, index=True)
    
    page_id = db.Column(db.String(100), nullable=True) # Connected Page ID
    page_name = db.Column(db.String(255), nullable=True)
    
    business_manager_id = db.Column(db.String(100), nullable=True)  # Optional for Page Token flow
    system_user_id = db.Column(db.String(100), nullable=True)  # Optional for Page Token flow
    encrypted_system_token = db.Column(db.Text, nullable=False) # STRICT NAME MATCH
    
    install_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), default="active") # active, disconnected
    
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    # Relationship to Company (Admin)
    admin = db.relationship("Admin", backref=db.backref("facebook_connection", uselist=False))

    def set_token(self, token):
        from app.utils.security import encrypt_value
        self.encrypted_system_token = encrypt_value(token)

    def get_token(self):
        from app.utils.security import decrypt_value
        return decrypt_value(self.encrypted_system_token)


# =========================================================
# FACEBOOK PAGE INTEGRATION (Legacy/Reference)
# =========================================================
class FacebookPage(db.Model):
    __tablename__ = "facebook_pages"

    id = db.Column(db.Integer, primary_key=True)
    
    # Linked to Company (Admin)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, index=True)
    
    # Optional: Link to Connection
    connection_id = db.Column(db.Integer, db.ForeignKey("facebook_connections.id"), nullable=True)
    
    page_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    page_name = db.Column(db.String(255), nullable=False)
    page_access_token = db.Column(db.Text, nullable=False)
    
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "page_id": self.page_id,
            "page_name": self.page_name,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =========================================================
# LEADS
# =========================================================
class Lead(db.Model):
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    # UPDATED: Linked to ADMIN (Company)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, index=True)
    
    # Facebook/IndiaMART specific ID (Scoped uniqueness per Admin)
    facebook_lead_id = db.Column(db.String(100), unique=False, nullable=True, index=True)
    form_id = db.Column(db.String(100), nullable=True)
    
    __table_args__ = (
        db.UniqueConstraint('admin_id', 'facebook_lead_id', name='_admin_lead_uc'),
    )
    
    # Contact Info
    name = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True, index=True)
    
    # Meta
    source = db.Column(db.String(50), default="facebook", index=True)
    status = db.Column(db.String(50), default="new", index=True) # new, contacted, qualified, converted, junk
    
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    
    # Real Estate Fields
    property_type = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    budget = db.Column(db.String(100), nullable=True)
    requirement = db.Column(db.Text, nullable=True) # Full description

    custom_fields = db.Column(JSONAuto()) # Store extra fields from FB form
    
    created_at = db.Column(db.DateTime, default=now, index=True)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    assignee = db.relationship("User", foreign_keys=[assigned_to], backref=db.backref("assigned_leads", lazy="dynamic"))

    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "facebook_lead_id": self.facebook_lead_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "source": self.source,
            "status": self.status,
            "assigned_to": self.assigned_to,
            "assigned_agent_name": self.assignee.name if self.assignee else None,
            "property_type": self.property_type,
            "location": self.location,
            "budget": self.budget,
            "requirement": self.requirement,
            "custom_fields": self.custom_fields,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =========================================================
# INDIAMART INTEGRATION
# =========================================================
class IndiamartSettings(db.Model):
    __tablename__ = "indiamart_settings"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, unique=True)
    
    mobile_number = db.Column(db.String(20), nullable=False)
    api_key = db.Column(db.String(100), nullable=False)
    
    last_sync_time = db.Column(db.DateTime, nullable=True)
    auto_sync_enabled = db.Column(db.Boolean, default=True) # NEW: Auto Sync Toggle
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    def set_api_key(self, key):
        from app.utils.security import encrypt_value
        self.api_key = encrypt_value(key)

    def get_api_key(self):
        from app.utils.security import decrypt_value
        return decrypt_value(self.api_key)

    def to_dict(self):
        # Determine strict or masked display? Always mask for UI.
        # Decrypt first to get last 4 digits
        real_key = self.get_api_key()
        masked = None
        if real_key:
            masked = "***" + real_key[-4:] if len(real_key) > 4 else "***"

        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "mobile_number": self.mobile_number,
            "api_key": masked,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "auto_sync_enabled": self.auto_sync_enabled,
            "created_at": self.created_at.isoformat()
        }


# =========================================================
# MAGICBRICKS INTEGRATION
# =========================================================
class MagicbricksSettings(db.Model):
    __tablename__ = "magicbricks_settings"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, unique=True)
    
    imap_host = db.Column(db.String(100), default="imap.gmail.com")
    email_id = db.Column(db.String(100), nullable=False)
    app_password = db.Column(db.String(255), nullable=False) # Encrypted
    
    last_sync_time = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    def set_app_password(self, pwd):
        from app.utils.security import encrypt_value
        self.app_password = encrypt_value(pwd)

    def get_app_password(self):
        from app.utils.security import decrypt_value
        return decrypt_value(self.app_password)

    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "email_id": self.email_id,
            "imap_host": self.imap_host,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "is_active": self.is_active,
            "is_connected": bool(self.app_password)
        }

class ProcessedEmail(db.Model):
    __tablename__ = "processed_emails"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False)
    message_id = db.Column(db.String(255), nullable=False) # Email Header Message-ID
    lead_source = db.Column(db.String(50), default="MAGICBRICKS")
    processed_at = db.Column(db.DateTime, default=now)

    __table_args__ = (
        db.UniqueConstraint('admin_id', 'message_id', name='uq_admin_message_id'),
    )


# =========================================================
# 99ACRES INTEGRATION
# =========================================================
class NinetyNineAcresSettings(db.Model):
    __tablename__ = "ninety_nine_acres_settings"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, unique=True)
    
    imap_host = db.Column(db.String(100), default="imap.gmail.com")
    email_id = db.Column(db.String(100), nullable=False)
    app_password = db.Column(db.String(255), nullable=False) # Encrypted
    
    last_sync_time = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    def set_app_password(self, pwd):
        from app.utils.security import encrypt_value
        self.app_password = encrypt_value(pwd)

    def get_app_password(self):
        from app.utils.security import decrypt_value
        return decrypt_value(self.app_password)


    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "email_id": self.email_id,
            "imap_host": self.imap_host,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "is_active": self.is_active,
            "is_connected": bool(self.app_password)
        }


# =========================================================
# JUSTDIAL INTEGRATION
# =========================================================
class JustDialSettings(db.Model):
    __tablename__ = "justdial_settings"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, unique=True)
    
    imap_host = db.Column(db.String(100), default="imap.gmail.com")
    email_id = db.Column(db.String(100), nullable=False)
    app_password = db.Column(db.String(255), nullable=False) # Encrypted
    
    last_sync_time = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    def set_app_password(self, pwd):
        from app.utils.security import encrypt_value
        self.app_password = encrypt_value(pwd)

    def get_app_password(self):
        from app.utils.security import decrypt_value
        return decrypt_value(self.app_password)


    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "email_id": self.email_id,
            "imap_host": self.imap_host,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "is_active": self.is_active,
            "is_connected": bool(self.app_password)
        }


# =========================================================
# HOUSING INTEGRATION
# =========================================================
class HousingSettings(db.Model):
    __tablename__ = "housing_settings"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, unique=True)
    
    imap_host = db.Column(db.String(100), default="imap.gmail.com")
    email_id = db.Column(db.String(100), nullable=False)
    app_password = db.Column(db.String(255), nullable=False) # Encrypted
    
    last_sync_time = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    def set_app_password(self, pwd):
        from app.utils.security import encrypt_value
        self.app_password = encrypt_value(pwd)

    def get_app_password(self):
        from app.utils.security import decrypt_value
        return decrypt_value(self.app_password)

    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "email_id": self.email_id,
            "imap_host": self.imap_host,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "is_active": self.is_active,
            "is_connected": bool(self.app_password)
        }


# =========================================================
# LEAD STATUS HISTORY
# =========================================================
class LeadStatusHistory(db.Model):
    __tablename__ = "lead_status_history"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    
    old_status = db.Column(db.String(50), nullable=True)
    new_status = db.Column(db.String(50), nullable=False)
    
    # Optional: Track who changed it (Admin or User)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    
    created_at = db.Column(db.DateTime, default=now)

    def to_dict(self):
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "created_at": self.created_at.isoformat()
        }


# =========================================================
# WHATSAPP CONFIG (Per Admin — Encrypted Credentials)
# =========================================================
class WhatsAppConfig(db.Model):
    __tablename__ = "whatsapp_configs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, unique=True, index=True)

    # Encrypted Meta credentials
    _access_token       = db.Column("access_token", db.Text, nullable=True)
    phone_number_id     = db.Column(db.String(100), nullable=True)
    waba_id             = db.Column(db.String(100), nullable=True)  # WhatsApp Business Account ID
    verify_token        = db.Column(db.String(255), nullable=True)  # Webhook verify token

    # Optional business profile cache
    business_name       = db.Column(db.String(255), nullable=True)
    phone_display       = db.Column(db.String(30), nullable=True)   # Human-readable number

    is_active           = db.Column(db.Boolean, default=True)
    created_at          = db.Column(db.DateTime, default=now)
    updated_at          = db.Column(db.DateTime, default=now, onupdate=now)

    admin = db.relationship("Admin", backref=db.backref("whatsapp_config", uselist=False))

    def set_token(self, token):
        from app.utils.security import encrypt_value
        self._access_token = encrypt_value(token)

    def get_token(self):
        from app.utils.security import decrypt_value
        if not self._access_token:
            return None
        return decrypt_value(self._access_token)

    def to_dict(self, mask_token=True):
        token = self.get_token()
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "phone_number_id": self.phone_number_id,
            "waba_id": self.waba_id,
            "verify_token": self.verify_token,
            "business_name": self.business_name,
            "phone_display": self.phone_display,
            "is_active": self.is_active,
            "is_connected": bool(token and self.phone_number_id),
            "access_token_masked": ("***" + token[-6:]) if (token and len(token) > 6 and mask_token) else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =========================================================
# WA CONTACT (Customer WhatsApp identity)
# =========================================================
class WAContact(db.Model):
    __tablename__ = "wa_contacts"

    id              = db.Column(db.Integer, primary_key=True)
    admin_id        = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, index=True)

    phone_number    = db.Column(db.String(30), nullable=False, index=True)  # E.164 format, e.g. 919876543210
    name            = db.Column(db.String(255), nullable=True)              # From Meta profile or manual
    profile_name    = db.Column(db.String(255), nullable=True)              # As returned by WhatsApp webhook

    # Optional: link to Lead if exists
    lead_id         = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=True, index=True)

    created_at      = db.Column(db.DateTime, default=now)
    updated_at      = db.Column(db.DateTime, default=now, onupdate=now)

    __table_args__ = (
        db.UniqueConstraint('admin_id', 'phone_number', name='uq_wacontact_admin_phone'),
    )

    admin           = db.relationship("Admin", backref=db.backref("wa_contacts", lazy="dynamic"))
    lead            = db.relationship("Lead", backref=db.backref("wa_contact", uselist=False))
    conversations   = db.relationship("WAConversation", back_populates="contact", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "phone_number": self.phone_number,
            "name": self.name or self.profile_name or self.phone_number,
            "profile_name": self.profile_name,
            "lead_id": self.lead_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =========================================================
# WA CONVERSATION (Thread per contact per admin)
# =========================================================
class WAConversation(db.Model):
    __tablename__ = "wa_conversations"

    id              = db.Column(db.Integer, primary_key=True)
    admin_id        = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, index=True)
    contact_id      = db.Column(db.Integer, db.ForeignKey("wa_contacts.id"), nullable=False, index=True)
    assigned_agent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    # Status: open, pending, closed
    status          = db.Column(db.String(20), default="open", index=True)

    # Counters & timestamps
    unread_count        = db.Column(db.Integer, default=0)
    last_message_at     = db.Column(db.DateTime, nullable=True, index=True)
    last_customer_msg_at = db.Column(db.DateTime, nullable=True)  # For 24h window check

    created_at      = db.Column(db.DateTime, default=now)
    updated_at      = db.Column(db.DateTime, default=now, onupdate=now)

    __table_args__ = (
        db.UniqueConstraint('admin_id', 'contact_id', name='uq_waconv_admin_contact'),
        db.Index('idx_waconv_admin_status', 'admin_id', 'status'),
        db.Index('idx_waconv_last_msg', 'admin_id', 'last_message_at'),
    )

    admin           = db.relationship("Admin", backref=db.backref("wa_conversations", lazy="dynamic"))
    contact         = db.relationship("WAContact", back_populates="conversations")
    assigned_agent  = db.relationship("User", backref=db.backref("wa_conversations", lazy="dynamic"))
    messages        = db.relationship("WAMessage", back_populates="conversation",
                                      order_by="WAMessage.created_at", lazy="dynamic")
    lock            = db.relationship("WAConversationLock", back_populates="conversation", uselist=False)

    def is_within_24h_window(self):
        """Return True if customer last messaged within 24 hours."""
        if not self.last_customer_msg_at:
            return False
        delta = datetime.utcnow() - self.last_customer_msg_at
        return delta.total_seconds() < 86400  # 24h in seconds

    def to_dict(self, include_last_message=False):
        # Treat expired locks as if there is no lock
        active_lock = self.lock if (self.lock and not self.lock.is_expired()) else None
        d = {
            "id": self.id,
            "admin_id": self.admin_id,
            "contact": self.contact.to_dict() if self.contact else None,
            "assigned_agent_id": self.assigned_agent_id,
            "assigned_agent_name": self.assigned_agent.name if self.assigned_agent else None,
            "status": self.status,
            "unread_count": self.unread_count,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "within_24h_window": self.is_within_24h_window(),
            "locked_by": active_lock.agent_id if active_lock else None,
            "locked_by_name": active_lock.agent.name if (active_lock and active_lock.agent) else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_last_message:
            last_msg = self.messages.order_by(None).order_by(WAMessage.created_at.desc()).first()
            d["last_message"] = last_msg.to_dict() if last_msg else None
        return d


# =========================================================
# WA MESSAGE
# =========================================================
class WAMessage(db.Model):
    __tablename__ = "wa_messages"

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("wa_conversations.id"), nullable=False, index=True)
    admin_id        = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, index=True)

    # Meta's message ID (wamid.xxx)
    whatsapp_msg_id = db.Column(db.String(255), nullable=True, unique=True, index=True)

    # Direction: customer → agent or agent → customer
    sender_type     = db.Column(db.String(20), nullable=False)   # 'customer', 'agent', 'system'
    sender_id       = db.Column(db.Integer, nullable=True)        # user.id if agent

    # Content
    message_type    = db.Column(db.String(30), default="text")    # text, image, video, audio, document, template, location, sticker
    message_text    = db.Column(db.Text, nullable=True)
    media_url       = db.Column(db.Text, nullable=True)           # Resolved public URL
    media_id        = db.Column(db.String(255), nullable=True)    # Meta media ID
    media_mime_type = db.Column(db.String(100), nullable=True)
    media_filename  = db.Column(db.String(255), nullable=True)
    caption         = db.Column(db.Text, nullable=True)

    # Template info (when message_type = 'template')
    template_name   = db.Column(db.String(255), nullable=True)

    # Context (reply-to)
    reply_to_wamid  = db.Column(db.String(255), nullable=True)

    # Delivery status (for outbound messages)
    # sent, delivered, read, failed
    status          = db.Column(db.String(20), default="sent")
    error_code      = db.Column(db.String(50), nullable=True)
    error_message   = db.Column(db.Text, nullable=True)

    created_at      = db.Column(db.DateTime, default=now, index=True)

    __table_args__ = (
        db.Index('idx_wamsg_conv_created', 'conversation_id', 'created_at'),
    )

    conversation    = db.relationship("WAConversation", back_populates="messages")
    status_logs     = db.relationship("WAMessageStatusLog", back_populates="message", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "whatsapp_msg_id": self.whatsapp_msg_id,
            "sender_type": self.sender_type,
            "sender_id": self.sender_id,
            "message_type": self.message_type,
            "message_text": self.message_text,
            "media_url": self.media_url,
            "media_id": self.media_id,
            "media_mime_type": self.media_mime_type,
            "media_filename": self.media_filename,
            "caption": self.caption,
            "template_name": self.template_name,
            "reply_to_wamid": self.reply_to_wamid,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =========================================================
# WA MESSAGE STATUS LOG (Delivery receipts)
# =========================================================
class WAMessageStatusLog(db.Model):
    __tablename__ = "wa_message_status_logs"

    id          = db.Column(db.Integer, primary_key=True)
    message_id  = db.Column(db.Integer, db.ForeignKey("wa_messages.id"), nullable=False, index=True)
    status      = db.Column(db.String(20), nullable=False)   # sent, delivered, read, failed
    timestamp   = db.Column(db.DateTime, default=now)
    raw_payload = db.Column(db.Text, nullable=True)          # Store raw Meta status object

    message     = db.relationship("WAMessage", back_populates="status_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "status": self.status,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# =========================================================
# WA TEMPLATE (Approved Meta templates cache)
# =========================================================
class WATemplate(db.Model):
    __tablename__ = "wa_templates"

    id              = db.Column(db.Integer, primary_key=True)
    admin_id        = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, index=True)

    template_id     = db.Column(db.String(100), nullable=True)    # Meta template ID
    name            = db.Column(db.String(255), nullable=False)
    language        = db.Column(db.String(20), default="en")
    category        = db.Column(db.String(50), nullable=True)      # MARKETING, UTILITY, AUTHENTICATION
    status          = db.Column(db.String(30), default="APPROVED") # APPROVED, PENDING, REJECTED

    # Parsed structure as JSON for quick re-use
    components      = db.Column(JSONAuto())                        # Header, Body, Footer, Buttons
    header_type     = db.Column(db.String(20), nullable=True)      # TEXT, IMAGE, VIDEO, DOCUMENT, NONE
    body_text       = db.Column(db.Text, nullable=True)            # Body text with {{1}} placeholders
    variable_count  = db.Column(db.Integer, default=0)            # # of {{n}} variables in body

    created_at      = db.Column(db.DateTime, default=now)
    synced_at       = db.Column(db.DateTime, default=now)         # Last sync from Meta

    __table_args__ = (
        db.UniqueConstraint('admin_id', 'name', 'language', name='uq_watemplate_admin_name_lang'),
    )

    admin = db.relationship("Admin", backref=db.backref("wa_templates", lazy="dynamic"))

    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "template_id": self.template_id,
            "name": self.name,
            "language": self.language,
            "category": self.category,
            "status": self.status,
            "header_type": self.header_type,
            "body_text": self.body_text,
            "variable_count": self.variable_count,
            "components": self.components,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
        }


# =========================================================
# WA CONVERSATION LOCK (Prevent simultaneous agent replies)
# =========================================================
class WAConversationLock(db.Model):
    __tablename__ = "wa_conversation_locks"

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("wa_conversations.id"), nullable=False, unique=True, index=True)
    # Stored as plain int — no FK so both admin and user IDs are valid holders
    agent_id        = db.Column(db.Integer, nullable=False)
    locked_at       = db.Column(db.DateTime, default=now)
    expires_at      = db.Column(db.DateTime, nullable=True)  # Auto-expire after e.g. 15 min of inactivity

    conversation    = db.relationship("WAConversation", back_populates="lock")

    @property
    def agent(self):
        """Resolve the lock holder — could be a User (agent) or an Admin.
        
        agent_id is stored without a FK so it can hold either ID type.
        Try User first (most common), then Admin as fallback.
        Returns None only if the ID cannot be resolved in either table.
        """
        holder = db.session.get(User, self.agent_id)
        if holder:
            return holder
        # Fallback: lock may be held by an Admin (e.g. admin opened the conversation)
        from app.models import Admin as _Admin
        return db.session.get(_Admin, self.agent_id)

    def is_expired(self):
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent.name if self.agent else None,
            "locked_at": self.locked_at.isoformat() if self.locked_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired(),
        }


# =========================================================
# WA LEAD ASSIGN CONFIG (Auto-send WA on lead assignment)
# =========================================================
class WALeadAssignConfig(db.Model):
    """
    Per-admin config for auto-WhatsApp on lead assignment.
    When a lead is assigned to an agent:
      • agent_template  → sent to the AGENT's phone
      • lead_template   → sent to the LEAD's phone

    Param lists support placeholders resolved at send time:
        {{lead_name}}, {{lead_phone}}, {{lead_source}},
        {{agent_name}}, {{agent_phone}}
    """
    __tablename__ = "wa_lead_assign_configs"

    id                  = db.Column(db.Integer, primary_key=True)
    admin_id            = db.Column(db.Integer, db.ForeignKey("admins.id"),
                                    nullable=False, unique=True, index=True)

    is_enabled          = db.Column(db.Boolean, default=False)

    # Template to send to the AGENT
    agent_template_name = db.Column(db.String(255), nullable=True)
    agent_params        = db.Column(JSONAuto())   # list[str] with {{placeholders}}
    agent_header_url    = db.Column(db.String(1000), nullable=True) # Optional media link

    # Template to send to the LEAD
    lead_template_name  = db.Column(db.String(255), nullable=True)
    lead_params         = db.Column(JSONAuto())   # list[str] with {{placeholders}}
    lead_header_url     = db.Column(db.String(1000), nullable=True) # Optional media link

    created_at          = db.Column(db.DateTime, default=now)
    updated_at          = db.Column(db.DateTime, default=now, onupdate=now)

    admin = db.relationship("Admin", backref=db.backref("wa_lead_assign_config", uselist=False))

    def to_dict(self):
        return {
            "id":                   self.id,
            "admin_id":             self.admin_id,
            "is_enabled":           self.is_enabled,
            "agent_template_name":  self.agent_template_name,
            "agent_params":         self.agent_params or [],
            "agent_header_url":     self.agent_header_url,
            "lead_template_name":   self.lead_template_name,
            "lead_params":          self.lead_params or [],
            "lead_header_url":      self.lead_header_url,
            "updated_at":           self.updated_at.isoformat() if self.updated_at else None,
        }
