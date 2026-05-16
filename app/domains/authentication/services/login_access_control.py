"""
Login Access Control for Africa SPA System

Enforces access control during login process.
"""

import logging
from flask import redirect, url_for, flash, session
from flask_login import current_user
from app.services.access_control import access_control_service

logger = logging.getLogger(__name__)

def check_login_access():
    """
    Check user access after login and redirect if necessary
    """
    try:
        if not current_user.is_authenticated:
            return None
        
        # Get user access permissions
        access = access_control_service.check_user_access(current_user)
        
        # If user cannot login, log them out
        if not access.get('can_login', False):
            logger.warning(f"Login denied for user {current_user.id}: {access.get('message', 'Unknown reason')}")
            flash(access.get('message', 'Access denied'), 'danger')
            return redirect(url_for('auth.logout'))
        
        # Check if redirect is needed
        redirect_url = access.get('redirect_url')
        if redirect_url:
            # Store message in session for after redirect
            if access.get('message'):
                flash(access.get('message'), 'warning')
            return redirect(redirect_url)
        
        return None
        
    except Exception as e:
        logger.error(f"Error checking login access: {str(e)}")
        # Allow login on error to prevent complete lockout
        return None

def enforce_access_after_login():
    """
    Function to be called after successful login to enforce access rules
    """
    try:
        # Get user access permissions
        access = access_control_service.check_user_access(current_user)
        
        # Store access info in session
        session['access_level'] = access.get('access_level', 'unknown')
        session['access_restrictions'] = access.get('restrictions', [])
        session['access_message'] = access.get('message', '')
        
        # Log access level change
        logger.info(f"User {current_user.id} ({current_user.role}) logged in with access level: {access.get('access_level')}")
        
        return access
        
    except Exception as e:
        logger.error(f"Error enforcing access after login: {str(e)}")
        return None

def get_user_access_context():
    """
    Get user access context for templates
    """
    try:
        if current_user.is_authenticated:
            access = access_control_service.check_user_access(current_user)
            return {
                'access_level': access.get('access_level', 'unknown'),
                'access_restrictions': access.get('restrictions', []),
                'access_message': access.get('message', ''),
                'can_login': access.get('can_login', False),
                'redirect_url': access.get('redirect_url')
            }
        return {}
    except Exception as e:
        logger.error(f"Error getting user access context: {str(e)}")
        return {}
