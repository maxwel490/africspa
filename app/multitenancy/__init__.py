"""
Multi-Tenancy Management Module

This module handles the core multi-tenant functionality including:
- Salon registration and management
- Subscription validation
- Tenant isolation
- Subdomain routing
- Billing integration
"""

from .decorators import tenant_required, subscription_required
from .utils import get_current_salon, get_salon_by_slug
from .middleware import TenantMiddleware

__all__ = [
    'tenant_required',
    'subscription_required', 
    'get_current_salon',
    'get_salon_by_slug',
    'TenantMiddleware'
]
