"""
Authentication domain routes.

Handles login, logout, password management, OAuth, and worker/staff creation.

Currently served by:
- auth_bp: login, logout, forgot_password, redirect_to_dashboard
- oauth_bp: oauth_login, google_callback, apple_callback, link/unlink OAuth
- admin_bp: create_worker, check_username, delete_worker, edit_profile
- accountant_bp: manage_staff, check_username, edit_staff, reset_password, delete_staff

The auth_bp and oauth_bp routes have been copied to this domain.
Worker management routes will be migrated incrementally.
"""
from flask import Blueprint

auth_domain_bp = Blueprint('auth_domain', __name__, url_prefix='/auth')
