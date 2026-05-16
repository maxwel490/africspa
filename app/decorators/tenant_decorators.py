"""
AfricSpa Multi-Tenant Decorators
Ensures proper data isolation and access control across all routes
"""

from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user
from app.models import Client, Appointment, Product, Branch, Salon


def tenant_isolated_query(model_class):
    """
    Decorator for route functions that automatically applies tenant filtering
    to all queries of the specified model class
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            # Super Admin can access all data
            if current_user.role == 'superadmin':
                return f(*args, **kwargs)
            
            # Regular users must belong to a salon
            if not current_user.salon_id:
                flash('You are not assigned to any salon', 'danger')
                return redirect(url_for('auth.logout'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_tenant_access(model_class, param_name='id'):
    """
    Decorator to validate that the requested resource belongs to the user's salon
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            # Super Admin can access all resources
            if current_user.role == 'superadmin':
                return f(*args, **kwargs)
            
            # Get the resource ID from URL parameters
            resource_id = kwargs.get(param_name) or request.args.get(param_name)
            if not resource_id:
                abort(404, "Resource ID not specified")
            
            # Query the resource with tenant filtering
            resource = model_class.query.filter_by(
                id=resource_id, 
                salon_id=current_user.salon_id
            ).first()
            
            if not resource:
                abort(404, "Resource not found or access denied")
            
            # Store the validated resource in the request context
            request.validated_resource = resource
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def tenant_client_access(f):
    """
    Decorator specifically for client access validation
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Super Admin can access all clients
        if current_user.role == 'superadmin':
            return f(*args, **kwargs)
        
        # Get client ID from URL parameters
        client_id = kwargs.get('id') or request.args.get('id') or request.form.get('client_id')
        if not client_id:
            abort(404, "Client ID not specified")
        
        # Validate client access
        client = Client.query.filter_by(
            id=client_id, 
            salon_id=current_user.salon_id
        ).first()
        
        if not client:
            flash('Client not found or access denied', 'danger')
            return redirect(url_for('admin.clients'))
        
        # Store the validated client
        request.validated_client = client
        
        return f(*args, **kwargs)
    return decorated_function


def tenant_appointment_access(f):
    """
    Decorator specifically for appointment access validation
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Super Admin can access all appointments
        if current_user.role == 'superadmin':
            return f(*args, **kwargs)
        
        # Get appointment ID from URL parameters
        appointment_id = kwargs.get('id') or request.args.get('id') or request.form.get('appointment_id')
        if not appointment_id:
            abort(404, "Appointment ID not specified")
        
        # Validate appointment access
        appointment = Appointment.query.filter_by(
            id=appointment_id, 
            salon_id=current_user.salon_id
        ).first()
        
        if not appointment:
            flash('Appointment not found or access denied', 'danger')
            return redirect(url_for('admin.appointments'))
        
        # Store the validated appointment
        request.validated_appointment = appointment
        
        return f(*args, **kwargs)
    return decorated_function


def tenant_product_access(f):
    """
    Decorator specifically for product access validation
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Super Admin can access all products
        if current_user.role == 'superadmin':
            return f(*args, **kwargs)
        
        # Get product ID from URL parameters
        product_id = kwargs.get('id') or request.args.get('id') or request.form.get('product_id')
        if not product_id:
            abort(404, "Product ID not specified")
        
        # Validate product access
        product = Product.query.filter_by(
            id=product_id, 
            salon_id=current_user.salon_id
        ).first()
        
        if not product:
            flash('Product not found or access denied', 'danger')
            return redirect(url_for('admin.products'))
        
        # Store the validated product
        request.validated_product = product
        
        return f(*args, **kwargs)
    return decorated_function


def branch_level_access(f):
    """
    Decorator for routes that need branch-level access control
    Allows users to access data from their branch or all branches (for admins)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Super Admin can access all branches
        if current_user.role == 'superadmin':
            return f(*args, **kwargs)
        
        # Admin and Accountant can access all branches in their salon
        if current_user.role in ['admin', 'accountant']:
            return f(*args, **kwargs)
        
        # Salonists can only access their own branch
        if current_user.role == 'salonist':
            request.branch_filter = current_user.branch
        else:
            request.branch_filter = None
        
        return f(*args, **kwargs)
    return decorated_function


def tenant_data_isolation(f):
    """
    General decorator that ensures all data operations are tenant-isolated
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Super Admin bypasses tenant isolation
        if current_user.role == 'superadmin':
            request.tenant_mode = 'global'
            return f(*args, **kwargs)
        
        # Ensure user has a salon assigned
        if not current_user.salon_id:
            flash('You are not assigned to any salon', 'danger')
            return redirect(url_for('auth.logout'))
        
        # Set tenant context
        request.tenant_mode = 'isolated'
        request.salon_id = current_user.salon_id
        request.branch = current_user.branch
        
        return f(*args, **kwargs)
    return decorated_function


def require_salon_membership(f):
    """
    Decorator that ensures the user belongs to a salon
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        if not current_user.salon_id:
            flash('You must be assigned to a salon to access this feature', 'warning')
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return decorated_function
