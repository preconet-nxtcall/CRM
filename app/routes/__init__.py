# from .super_admin import bp as super_admin_bp
# from .admin import bp as admin_bp
# from .users import bp as users_bp


# __all__ = ['super_admin_bp', 'admin_bp', 'users_bp']


from .super_admin import bp as super_admin
from .admin import bp as admin
from .users import bp as users

__all__ = ["super_admin", "admin", "users"]