"""
AfricSpa Tenant Isolation Middleware
Ensures complete data isolation between tenants
"""

from flask import g, request, redirect, url_for, flash
from flask_login import current_user
from app.models import Salon, Worker


class TenantIsolationMiddleware:
    """Middleware to enforce tenant isolation across all requests"""
    
    def __init__(self, app):
        self.app = app
        app.before_request(self.before_request)
    
    def before_request(self):
        """Execute before each request to enforce tenant isolation"""
        
        # Skip tenant isolation for static files and auth routes
        if request.endpoint and (
            request.endpoint.startswith('static') or 
            request.endpoint.startswith('auth.') or
            request.endpoint in ['main.index', 'main.about', 'main.services', 'main.gallery', 'main.beautyspace', 'main.booking', 'main.contact']
        ):
            return
        
        # Set tenant context for authenticated users
        if current_user.is_authenticated:
            # Super Admin bypasses tenant isolation
            if current_user.role == 'superadmin':
                g.tenant_mode = 'global'
                g.salon_id = None
                g.salon = None
                return
            
            # Ensure user has a salon assigned
            if not current_user.salon_id:
                flash('You are not assigned to any salon. Please contact support.', 'danger')
                return redirect(url_for('auth.logout'))
            
            # Get salon information
            salon = Salon.query.get(current_user.salon_id)
            if not salon or not salon.is_active:
                flash('Your salon is not active. Please contact support.', 'danger')
                return redirect(url_for('auth.logout'))
            
            # Set tenant context
            g.tenant_mode = 'isolated'
            g.salon_id = current_user.salon_id
            g.salon = salon
            g.branch = current_user.branch
            
            # Add tenant isolation headers for debugging
            if self.app.debug:
                g.tenant_headers = {
                    'X-Tenant-ID': str(salon.id),
                    'X-Tenant-Name': salon.name,
                    'X-Tenant-Slug': salon.slug,
                    'X-User-Branch': current_user.branch or 'None'
                }
        else:
            # Unauthenticated users get no tenant context
            g.tenant_mode = 'none'
            g.salon_id = None
            g.salon = None


def get_tenant_context():
    """Get current tenant context"""
    return {
        'mode': getattr(g, 'tenant_mode', 'none'),
        'salon_id': getattr(g, 'salon_id', None),
        'salon': getattr(g, 'salon', None),
        'branch': getattr(g, 'branch', None)
    }


def require_tenant_context():
    """Ensure tenant context is available for the current request"""
    context = get_tenant_context()
    
    if context['mode'] == 'none' and current_user.is_authenticated:
        return False
    
    if context['mode'] == 'isolated' and not context['salon']:
        return False
    
    return True


def get_tenant_filter(model_class):
    """Get tenant filter for database queries"""
    context = get_tenant_context()
    
    if context['mode'] == 'global':
        # Super Admin - no filtering
        return True
    
    if context['mode'] == 'isolated' and context['salon_id']:
        # Regular user - filter by salon_id
        return model_class.salon_id == context['salon_id']
    
    # No tenant context - deny access
    return False


class TenantQueryFilter:
    """Helper class to apply tenant filtering to queries"""
    
    @staticmethod
    def apply_filter(query, model_class):
        """Apply tenant filtering to a query"""
        context = get_tenant_context()
        
        if context['mode'] == 'global':
            # Super Admin - no filtering
            return query
        
        if context['mode'] == 'isolated' and context['salon_id']:
            # Regular user - filter by salon_id
            return query.filter(model_class.salon_id == context['salon_id'])
        
        # No tenant context - return empty query
        return query.filter(False)


def validate_tenant_access(resource):
    """Validate that the current user can access the specified resource"""
    context = get_tenant_context()
    
    if context['mode'] == 'global':
        # Super Admin can access everything
        return True
    
    if context['mode'] == 'isolated' and context['salon_id']:
        # Check if resource belongs to the user's salon
        if hasattr(resource, 'salon_id'):
            return resource.salon_id == context['salon_id']
        
        # For models without salon_id, deny access
        return False
    
    # No tenant context - deny access
    return False


def get_tenant_info():
    """Get formatted tenant information for display"""
    context = get_tenant_context()
    
    if context['mode'] == 'global':
        return {
            'name': 'Super Admin',
            'type': 'Global',
            'access': 'All Salons',
            'isolation': 'None'
        }
    
    if context['mode'] == 'isolated' and context['salon']:
        return {
            'name': context['salon'].name,
            'type': 'Isolated Tenant',
            'access': context['salon'].name,
            'isolation': 'Complete',
            'plan': 'Standard',
            'branch': context['branch']
        }
    
    return {
        'name': 'Guest',
        'type': 'No Access',
        'access': 'None',
        'isolation': 'N/A'
    }


def tenant_aware_template_context():
    """Add tenant context to template rendering"""
    context = get_tenant_context()
    
    return {
        'tenant_mode': context['mode'],
        'current_salon': context['salon'],
        'tenant_branch': context['branch'],
        'tenant_info': get_tenant_info()
    }
