from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user
from app.models import Branch

def roles_required(*roles):
    """
    Ensures the user has one of the allowed roles (e.g., 'admin', 'accountant').
    The 'wrapper' and 'decorated_view' ensure the original function's metadata is preserved.
    """
    def wrapper(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            # 1. First Exclamation/Flash: Check if authenticated and has role
            if not current_user.is_authenticated or current_user.role not in roles:
                flash("You do not have the required permissions to access this page.", "danger")
                abort(403) 
            return f(*args, **kwargs)
        return decorated_view
    return wrapper

def branch_required(f):
    """
    Ensures accountants and salonists only access data for their assigned branch.
    Admins are exempted for global oversight across all active branches.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        # 2. Second Exclamation/Flash: Check if branch is assigned
        if current_user.role != 'admin' and not current_user.branch:
            active_branches = ', '.join([b.name for b in Branch.query.filter_by(is_active=True).all()])
            flash(f"Access Denied: Your account is not assigned to a branch ({active_branches}).", "warning")
            return redirect(url_for('auth.login'))
            
        return f(*args, **kwargs)
    return wrapper