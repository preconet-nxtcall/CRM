# from flask_sqlalchemy import SQLAlchemy
# from flask_jwt_extended import JWTManager

# db = SQLAlchemy()
# jwt = JWTManager()

# app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager

# ----------------------------------------
# Database with Naming Conventions
# ----------------------------------------

# Prevents Alembic migration errors for foreign keys & constraints
from sqlalchemy import MetaData

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)

db = SQLAlchemy(metadata=metadata)

# ----------------------------------------
# JWT Manager
# ----------------------------------------

jwt = JWTManager()

# ----------------------------------------
# JWT Error Handlers
# ----------------------------------------

@jwt.unauthorized_loader
def unauthorized_callback(e):
    return {"error": "Missing or invalid JWT token"}, 401


@jwt.invalid_token_loader
def invalid_token_callback(e):
    return {"error": "Invalid token"}, 401


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return {"error": "Token expired"}, 401


@jwt.needs_fresh_token_loader
def needs_fresh_token_callback(jwt_header, jwt_payload):
    return {"error": "Fresh token required"}, 401


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return {"error": "Token has been revoked"}, 401


# ----------------------------------------
# Optional: Add custom claims if needed
# ----------------------------------------

# Example: automatically include role based on user/admin
# (Only enable if your logic needs it)
#
# @jwt.additional_claims_loader
# def add_claims(identity):
#     # detect role from DB
#     from app.models import User, Admin
#     if Admin.query.get(identity):
#         return {"role": "admin"}
#     return {"role": "user"}

# ----------------------------------------
# Initialize function
# ----------------------------------------

def init_extensions(app):
    """Call this inside your app factory"""
    db.init_app(app)
    jwt.init_app(app)
    return app