"""
Tenancy domain routes.

Handles salon/tenant management, branch management, and salon settings.

Currently served by:
- superadmin_bp: manage_salons, create_salon, view_salon, toggle_salon
- admin_bp: manage_branches, salon_settings

These routes will be migrated here incrementally.
"""
from flask import Blueprint

tenancy_bp = Blueprint('tenancy', __name__, url_prefix='/tenancy')
