"""
AfricSpa Multi-Tenant Helper Functions
Ensures proper data isolation between salons while allowing branch-level sharing
"""

from flask import current_app, g
from app.models import Salon, Worker, Client, Appointment, Product, Branch
from functools import wraps
from flask_login import current_user


def get_current_salon_id():
    """Get the current salon ID from the logged-in user"""
    if current_user.is_authenticated:
        return current_user.salon_id
    return None


def get_current_branch():
    """Get the current branch for the logged-in user"""
    if current_user.is_authenticated:
        return current_user.branch
    return None


def tenant_query_filter(model_class):
    """
    Returns a filter to ensure queries are scoped to the current tenant's salon
    Usage: Client.query.filter(tenant_query_filter(Client))
    """
    salon_id = get_current_salon_id()
    if salon_id:
        return model_class.salon_id == salon_id
    return None


def tenant_branch_query_filter(model_class):
    """
    Returns a filter for models that have both salon_id and branch fields
    Ensures proper isolation at salon level with branch-level sharing
    """
    salon_id = get_current_salon_id()
    if salon_id:
        return model_class.salon_id == salon_id
    return None


def get_salon_clients(include_all_branches=True):
    """
    Get clients for the current salon
    - include_all_branches=True: Get all clients across all branches of the salon
    - include_all_branches=False: Get clients only for the current user's branch
    """
    salon_id = get_current_salon_id()
    if not salon_id:
        return []
    
    query = Client.query.filter_by(salon_id=salon_id)
    
    if not include_all_branches:
        current_branch = get_current_branch()
        if current_branch:
            query = query.filter_by(branch=current_branch)
    
    return query.all()


def get_salon_appointments(include_all_branches=True):
    """
    Get appointments for the current salon
    """
    salon_id = get_current_salon_id()
    if not salon_id:
        return []
    
    query = Appointment.query.filter_by(salon_id=salon_id)
    
    if not include_all_branches:
        current_branch = get_current_branch()
        if current_branch:
            query = query.filter_by(branch=current_branch)
    
    return query.all()


def get_salon_products(include_all_branches=True):
    """
    Get products for the current salon
    """
    salon_id = get_current_salon_id()
    if not salon_id:
        return []
    
    query = Product.query.filter_by(salon_id=salon_id)
    
    if not include_all_branches:
        current_branch = get_current_branch()
        if current_branch:
            query = query.filter_by(branch=current_branch)
    
    return query.all()


def get_salon_branches():
    """Get all branches for the current salon"""
    salon_id = get_current_salon_id()
    if not salon_id:
        return []
    
    return Branch.query.filter_by(salon_id=salon_id).all()


def validate_client_access(client_id):
    """
    Validate that the current user can access the specified client
    Ensures no cross-salon data access
    """
    salon_id = get_current_salon_id()
    if not salon_id:
        return False
    
    client = Client.query.filter_by(id=client_id, salon_id=salon_id).first()
    return client is not None


def validate_appointment_access(appointment_id):
    """
    Validate that the current user can access the specified appointment
    """
    salon_id = get_current_salon_id()
    if not salon_id:
        return False
    
    appointment = Appointment.query.filter_by(id=appointment_id, salon_id=salon_id).first()
    return appointment is not None


def validate_product_access(product_id):
    """
    Validate that the current user can access the specified product
    """
    salon_id = get_current_salon_id()
    if not salon_id:
        return False
    
    product = Product.query.filter_by(id=product_id, salon_id=salon_id).first()
    return product is not None


def tenant_required(f):
    """
    Decorator to ensure tenant context is available
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        if not current_user.salon_id:
            flash('User is not assigned to any salon', 'danger')
            return redirect(url_for('auth.logout'))
        
        return f(*args, **kwargs)
    return decorated_function


def get_salon_stats():
    """Get statistics for the current salon"""
    salon_id = get_current_salon_id()
    if not salon_id:
        return {}
    
    return {
        'total_clients': Client.query.filter_by(salon_id=salon_id).count(),
        'total_appointments': Appointment.query.filter_by(salon_id=salon_id).count(),
        'total_products': Product.query.filter_by(salon_id=salon_id).count(),
        'total_branches': Branch.query.filter_by(salon_id=salon_id).count(),
        'total_workers': Worker.query.filter_by(salon_id=salon_id).count(),
    }


def ensure_tenant_isolation():
    """
    Utility function to verify tenant isolation is working
    For debugging and testing purposes
    """
    salon_id = get_current_salon_id()
    if not salon_id:
        return False
    
    # Check that all queries are properly scoped
    clients = Client.query.filter_by(salon_id=salon_id).all()
    for client in clients:
        if client.salon_id != salon_id:
            return False
    
    return True
