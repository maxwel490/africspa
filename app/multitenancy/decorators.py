"""
Multi-Tenancy Decorators

These decorators ensure proper tenant isolation and subscription validation.
"""

from functools import wraps
from flask import flash, redirect, url_for, request, abort
from flask_login import current_user
from app.models import Salon, Worker
from flask import current_app
import datetime

def tenant_required(f):
    """
    Ensures the user has a valid salon context.
    For salon-level users (admin, accountant, salonist).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Super admin can access any route
        if current_user.role == 'superadmin':
            return f(*args, **kwargs)
        
        # Get salon from session or user
        salon_id = request.args.get('salon_id') or session.get('salon_id')
        
        if not salon_id:
            flash('Please select a salon to continue', 'warning')
            return redirect(url_for('auth.select_salon'))
        
        # Verify user belongs to this salon
        salon = Salon.query.get(salon_id)
        if not salon or not salon.is_active:
            flash('Invalid or inactive salon', 'danger')
            return redirect(url_for('auth.select_salon'))
        
        # Check if user has access to this salon
        if current_user.salon_id != salon.id:
            flash('You do not have access to this salon', 'danger')
            return redirect(url_for('auth.select_salon'))
        
        # Store current salon in context
        request.current_salon = salon
        
        return f(*args, **kwargs)
    
    return decorated_function

def subscription_required():
    """
    Ensures the salon has an active subscription
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            salon = Salon.query.filter_by(id=current_user.salon_id).first()
            if not salon:
                return redirect(url_for('auth.login'))
            
            # Check if subscription is active
            if not salon.is_active or not salon.subscription_expires or salon.subscription_expires < datetime.datetime.utcnow():
                flash('Your subscription has expired. Please renew to continue.', 'warning')
                return redirect(url_for('billing.renew'))
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def salon_limit_required(limit_type='branches'):
    """
    Ensures the salon hasn't exceeded their plan limits.
    limit_type: branches, staff, clients
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            # Super admin bypasses limits
            if current_user.role == 'superadmin':
                return f(*args, **kwargs)
            
            salon = getattr(request, 'current_salon', None)
            if not salon:
                salon = Salon.query.get(current_user.salon_id)
            
            if not salon:
                flash('Salon not found', 'danger')
                return redirect(url_for('auth.select_salon'))
            
            # Check limits based on subscription plan
            # No limits - unlimited branches, staff, and clients
            plan_limits = {'branches': None, 'staff': None, 'clients': None}
            current_limit = plan_limits.get(limit_type, 0)
            
            # Count current usage
            if limit_type == 'branches':
                from app.models import Branch
                current_count = Branch.query.filter_by(salon_id=salon.id).count()
                limit_name = 'branches'
            elif limit_type == 'staff':
                current_count = Worker.query.filter_by(salon_id=salon.id).count()
                limit_name = 'staff members'
            elif limit_type == 'clients':
                from app.models import Client
                current_count = Client.query.filter_by(salon_id=salon.id).count()
                limit_name = 'clients'
            else:
                return f(*args, **kwargs)
            
            if current_limit is not None and current_count >= current_limit:
                flash(f'You have reached your limit of {current_limit} {limit_name}', 'warning')
                return redirect(url_for('billing.upgrade'))
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def api_tenant_required(f):
    """
    Tenant validation for API endpoints.
    Returns JSON error responses instead of redirects.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return {'error': 'Authentication required'}, 401
        
        # Get salon from header or parameter
        salon_id = request.headers.get('X-Salon-ID') or request.args.get('salon_id')
        
        if not salon_id:
            return {'error': 'Salon ID required'}, 400
        
        salon = Salon.query.get(salon_id)
        if not salon or not salon.is_active:
            return {'error': 'Invalid or inactive salon'}, 400
        
        if current_user.role != 'superadmin' and current_user.salon_id != salon.id:
            return {'error': 'Access denied'}, 403
        
        request.current_salon = salon
        return f(*args, **kwargs)
    
    return decorated_function
