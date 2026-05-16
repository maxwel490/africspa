"""
Multi-Tenancy Utilities

Helper functions for managing multi-tenant operations.
"""

from flask import request, session, current_app
from flask_login import current_user
from app.models import Salon
from werkzeug.local import LocalProxy

def get_current_salon():
    """
    Get the current salon from request context.
    Used by decorators and middleware.
    """
    return getattr(request, 'current_salon', None)

def get_salon_by_slug(slug):
    """
    Get salon by slug (for subdomain routing).
    """
    return Salon.query.filter_by(slug=slug, is_active=True).first()

def get_user_salons(user=None):
    """
    Get all salons a user has access to.
    Super admins see all salons, regular users see only their salon.
    """
    if user is None:
        user = current_user
    
    if not user or not user.is_authenticated:
        return []
    
    if user.role == 'superadmin':
        return Salon.query.all()
    else:
        salon = Salon.query.get(user.salon_id)
        return [salon] if salon else []

def set_current_salon(salon_id):
    """
    Set the current salon in session for tenant context.
    """
    session['salon_id'] = salon_id
    session.permanent = True

def clear_current_salon():
    """
    Clear the current salon from session.
    """
    session.pop('salon_id', None)

def validate_salon_access(salon, user=None):
    """
    Validate if user has access to the specified salon.
    """
    if user is None:
        user = current_user
    
    if not user or not user.is_authenticated:
        return False
    
    # Super admins can access any salon
    if user.role == 'superadmin':
        return True
    
    # Regular users can only access their assigned salon
    return user.salon_id == salon.id

def get_salon_context():
    """
    Get salon context for database queries.
    Returns salon_id for filtering queries.
    """
    salon = get_current_salon()
    if salon:
        return salon.id
    return None

def is_salon_limit_reached(salon, limit_type):
    """
    Check if salon has reached their subscription limits.
    """
    from app.models import Worker, Branch, Client
    
    # No plan limits - unlimited branches, staff, and clients
    plan_limits = {'branches': None, 'staff': None, 'clients': None}
    max_allowed = plan_limits.get(limit_type, 0)
    
    if limit_type == 'branches':
        current_count = Branch.query.filter_by(salon_id=salon.id).count()
    elif limit_type == 'staff':
        current_count = Worker.query.filter_by(salon_id=salon.id).count()
    elif limit_type == 'clients':
        from app.models import Client
        current_count = Client.query.filter_by(salon_id=salon.id).count()
    else:
        return False
    
    return current_count >= max_allowed

def get_subscription_features(salon):
    """
    Get features available - all features available for all salons.
    """
    return [
        'appointment_booking',
        'client_management',
        'multi_branch',  # Unlimited branches
        'advanced_analytics',
        'appointment_scheduling',
        'inventory_management',
        'staff_management',
        'reporting',
        'basic_reporting'
    ]

def calculate_subscription_cost(branch_count=1, billing_period='monthly'):
    """
    Calculate subscription cost - $30 per branch.
    """
    base_cost_per_branch = 30 * 120  # $30 in KES
    
    if billing_period == 'quarterly':
        return branch_count * base_cost_per_branch * 3
    elif billing_period == 'annually':
        return branch_count * base_cost_per_branch * 12
    else:
        return branch_count * base_cost_per_branch

def format_currency(amount):
    """
    Format amount as Kenyan Shillings.
    """
    return f"KES {amount:,.0f}"

def get_salon_performance_metrics(salon_id, days=30):
    """
    Get performance metrics for a salon over specified period.
    """
    from app.models import Appointment, Client, Worker
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Appointment metrics
    total_appointments = Appointment.query.filter(
        Appointment.salon_id == salon_id,
        Appointment.appointment_time >= start_date
    ).count()
    
    completed_appointments = Appointment.query.filter(
        Appointment.salon_id == salon_id,
        Appointment.appointment_time >= start_date,
        Appointment.status == 'Completed'
    ).count()
    
    # Client metrics
    new_clients = Client.query.filter(
        Client.salon_id == salon_id,
        Client.created_at >= start_date
    ).count()
    
    # Staff metrics
    active_staff = Worker.query.filter(
        Worker.salon_id == salon_id,
        Worker.is_active == True
    ).count()
    
    return {
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'completion_rate': (completed_appointments / total_appointments * 100) if total_appointments > 0 else 0,
        'new_clients': new_clients,
        'active_staff': active_staff,
        'period_days': days
    }

# Create a proxy for easy access to current salon
current_salon = LocalProxy(get_current_salon)
