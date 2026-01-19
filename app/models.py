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

    created_at = db.Column(db.DateTime, default=now)

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
    start_time = db.Column(db.DateTime, nullable=False)
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
# FACEBOOK PAGE INTEGRATION
# =========================================================
class FacebookPage(db.Model):
    __tablename__ = "facebook_pages"

    id = db.Column(db.Integer, primary_key=True)
    # UPDATED: Linked to ADMIN (Company) instead of User (Agent)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False, index=True)
    
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
    source = db.Column(db.String(50), default="facebook")
    status = db.Column(db.String(50), default="new") # new, contacted, qualified, converted, junk
    
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    
    custom_fields = db.Column(JSONAuto()) # Store extra fields from FB form
    
    created_at = db.Column(db.DateTime, default=now)
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
            "created_at": self.created_at.isoformat()
        }

