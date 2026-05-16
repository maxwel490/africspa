"""
Access Control Middleware for Africa SPA System

Enforces access control based on subscription status and grace periods.
"""

import logging
from functools import wraps
from flask import request, redirect, url_for, flash, abort
from flask_login import current_user
from app.services.access_control import access_control_service

logger = logging.getLogger(__name__)

def access_control_middleware(f):
    """
    Middleware decorator to enforce access control on routes
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip access control for auth routes and static files
        if request.endpoint and (
            request.endpoint.startswith('auth.') or 
            request.endpoint == 'static' or
            request.endpoint in ['index']
        ):
            return f(*args, **kwargs)
        
        # Skip if user not logged in (login_required will handle it)
        if not current_user.is_authenticated:
            return f(*args, **kwargs)
        
        try:
            # Check user access
            access = access_control_service.check_user_access(current_user)
            
            # If user cannot login, abort with 403
            if not access.get('can_login', False):
                logger.warning(f"Access denied for user {current_user.id}: {access.get('message', 'Unknown reason')}")
                abort(403)
            
            # Check route access
            route_path = request.path
            if not access_control_service.can_access_route(current_user, route_path):
                # Get redirect URL
                redirect_url = access.get('redirect_url')
                if redirect_url and redirect_url != route_path:
                    # Show message before redirect
                    if access.get('message'):
                        flash(access.get('message'), 'warning')
                    return redirect(redirect_url)
                else:
                    abort(403)
            
            return f(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Access control middleware error: {str(e)}")
            # Allow access on error to prevent complete lockout
            return f(*args, **kwargs)
    
    return decorated_function

def role_required(*roles):
    """
    Decorator to require specific roles
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def subscription_required(f):
    """
    Decorator to require active subscription
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Superadmin bypasses subscription check
        if current_user.role == 'superadmin':
            return f(*args, **kwargs)
        
        # Check subscription status
        if current_user.salon_id:
            access = access_control_service.check_user_access(current_user)
            
            if not access.get('can_login', False):
                flash('Your subscription is not active. Please update your payment method.', 'warning')
                return redirect(url_for('subscription_payment.billing_dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def billing_redirect(f):
    """
    Decorator to redirect admin to billing if payment is due
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Only apply to admin users
        if current_user.role == 'admin' and current_user.salon_id:
            access = access_control_service.check_user_access(current_user)
            
            # If access level is billing_only, redirect to billing
            if access.get('access_level') == 'billing_only':
                flash('Payment required to continue using the system.', 'warning')
                return redirect(url_for('subscription_payment.billing_dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def service_orders_only(f):
    """
    Decorator to restrict access to service orders only
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Check if user has service orders only access
        access = access_control_service.check_user_access(current_user)
        restrictions = access.get('restrictions', [])
        
        if 'service_orders_only' in restrictions:
            # Allow access to service order routes
            if not request.path.startswith('/service_orders'):
                flash('Access limited to service orders only during grace period.', 'warning')
                return redirect(url_for('admin.service_orders_analysis'))
        
        return f(*args, **kwargs)
    return decorated_function

def no_services_access(f):
    """
    Decorator to deny access to service management routes
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Check if user has no services restriction
        access = access_control_service.check_user_access(current_user)
        restrictions = access.get('restrictions', [])
        
        if 'no_services' in restrictions:
            # Deny access to service management routes
            if request.path.startswith('/services') or request.path.startswith('/appointments'):
                flash('Service management access restricted during grace period.', 'warning')
                return redirect(url_for('admin.service_orders_analysis'))
        
        return f(*args, **kwargs)
    return decorated_function

def no_inventory_access(f):
    """
    Decorator to deny access to inventory management routes
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Check if user has no inventory restriction
        access = access_control_service.check_user_access(current_user)
        restrictions = access.get('restrictions', [])
        
        if 'no_inventory' in restrictions:
            # Deny access to inventory routes
            if request.path.startswith('/stock') or request.path.startswith('/inventory') or request.path.startswith('/products'):
                flash('Inventory management access restricted during grace period.', 'warning')
                return redirect(url_for('admin.service_orders_analysis'))
        
        return f(*args, **kwargs)
    return decorated_function
