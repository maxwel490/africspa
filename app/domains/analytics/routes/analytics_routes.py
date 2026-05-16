"""
Analytics domain routes.

Handles reporting, system analytics, platform statistics, and system configuration.

Currently served by:
- superadmin_bp: analytics, api_stats, settings
- admin_bp: dashboard (analytics components)

These routes will be migrated here incrementally.
"""
from flask import Blueprint

analytics_bp = Blueprint('analytics', __name__, url_prefix='/analytics')
