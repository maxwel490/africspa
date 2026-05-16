"""
OAuth Authentication Routes for Africa SPA System

Handles Google and Apple (iCloud) OAuth authentication flows
"""

from flask import Blueprint, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from app.auth.oauth_providers import oauth_manager
from app.models import Worker, db
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

oauth_bp = Blueprint('oauth', __name__)

@oauth_bp.route('/login/<provider>')
def oauth_login(provider):
    """Initiate OAuth login with specified provider"""
    
    oauth_provider = oauth_manager.get_provider(provider)
    if not oauth_provider:
        flash(f'OAuth provider {provider} is not available', 'danger')
        return redirect(url_for('auth.login'))
    
    auth_url = oauth_provider.get_authorization_url()
    return redirect(auth_url)

@oauth_bp.route('/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    
    code = request.args.get('code')
    error = request.args.get('error')
    
    user, message = oauth_manager.handle_oauth_callback('google', code, error)
    
    if user and user.is_authenticated:
        # Successful login
        if user.role == 'pending':
            flash('Your account is pending admin approval. Please contact your administrator.', 'warning')
            logout_user()
            return redirect(url_for('auth.login'))
        elif user.role == 'superadmin':
            return redirect(url_for('superadmin.dashboard'))
        elif user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'accountant':
            return redirect(url_for('accountant.dashboard'))
        elif user.role == 'salonist':
            return redirect(url_for('salonist.dashboard'))
        else:
            return redirect(url_for('main.index'))
    else:
        # Failed login
        if message:
            flash(message, 'danger')
        return redirect(url_for('auth.login'))

@oauth_bp.route('/apple/callback', methods=['GET', 'POST'])
def apple_callback():
    """Handle Apple Sign In callback"""
    
    if request.method == 'POST':
        # Apple Sign In returns POST data
        code = request.form.get('code')
        state = request.form.get('state')
    else:
        # Fallback for GET requests
        code = request.args.get('code')
        state = request.args.get('state')
    
    error = request.args.get('error') or request.form.get('error')
    
    user, message = oauth_manager.handle_oauth_callback('apple', code, error)
    
    if user and user.is_authenticated:
        # Successful login
        if user.role == 'pending':
            flash('Your account is pending admin approval. Please contact your administrator.', 'warning')
            logout_user()
            return redirect(url_for('auth.login'))
        elif user.role == 'superadmin':
            return redirect(url_for('superadmin.dashboard'))
        elif user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'accountant':
            return redirect(url_for('accountant.dashboard'))
        elif user.role == 'salonist':
            return redirect(url_for('salonist.dashboard'))
        else:
            return redirect(url_for('main.index'))
    else:
        # Failed login
        if message:
            flash(message, 'danger')
        return redirect(url_for('auth.login'))

@oauth_bp.route('/link/<provider>')
@login_required
def link_oauth_account(provider):
    """Link OAuth account to current user"""
    
    oauth_provider = oauth_manager.get_provider(provider)
    if not oauth_provider:
        flash(f'OAuth provider {provider} is not available', 'danger')
        return redirect(url_for('auth.profile'))
    
    # Store user ID in session for linking after callback
    session['link_oauth_user_id'] = current_user.id
    session['link_oauth_provider'] = provider
    
    auth_url = oauth_provider.get_authorization_url()
    return redirect(auth_url)

@oauth_bp.route('/unlink/<provider>')
@login_required
def unlink_oauth_account(provider):
    """Unlink OAuth account from current user"""
    
    if not current_user.preferences:
        flash('No OAuth accounts linked', 'info')
        return redirect(url_for('auth.profile'))
    
    try:
        prefs = json.loads(current_user.preferences)
        
        if provider == 'google' and 'google_id' in prefs:
            del prefs['google_id']
            del prefs['google_picture']
            del prefs['oauth_provider']
            flash('Google account unlinked successfully', 'success')
        elif provider == 'apple' and 'apple_id' in prefs:
            del prefs['apple_id']
            del prefs['oauth_provider']
            flash('Apple account unlinked successfully', 'success')
        else:
            flash(f'No {provider} account linked', 'info')
        
        current_user.preferences = json.dumps(prefs)
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error unlinking OAuth account: {str(e)}")
        flash('Error unlinking OAuth account', 'danger')
    
    return redirect(url_for('auth.profile'))

@oauth_bp.route('/link/callback/<provider>')
def link_oauth_callback(provider):
    """Handle OAuth callback for linking accounts"""
    
    code = request.args.get('code')
    error = request.args.get('error')
    
    # Get user ID from session
    user_id = session.get('link_oauth_user_id')
    link_provider = session.get('link_oauth_provider')
    
    if not user_id or link_provider != provider:
        flash('Invalid OAuth linking request', 'danger')
        return redirect(url_for('auth.login'))
    
    # Clear session
    session.pop('link_oauth_user_id', None)
    session.pop('link_oauth_provider', None)
    
    oauth_provider = oauth_manager.get_provider(provider)
    if not oauth_provider:
        flash(f'OAuth provider {provider} is not available', 'danger')
        return redirect(url_for('auth.profile'))
    
    try:
        # Exchange code for access token
        token_data = oauth_provider.get_access_token(code)
        if not token_data:
            flash('Failed to link OAuth account', 'danger')
            return redirect(url_for('auth.profile'))
        
        access_token = token_data.get('access_token')
        if not access_token:
            flash('Failed to link OAuth account', 'danger')
            return redirect(url_for('auth.profile'))
        
        # Get user information
        user_info = oauth_provider.get_user_info(access_token)
        if not user_info:
            flash('Failed to get OAuth account information', 'danger')
            return redirect(url_for('auth.profile'))
        
        # Link OAuth account to current user
        current_user = Worker.query.get(user_id)
        if not current_user:
            flash('User not found', 'danger')
            return redirect(url_for('auth.login'))
        
        if not current_user.preferences:
            current_user.preferences = json.dumps({})
        
        prefs = json.loads(current_user.preferences)
        
        if provider == 'google':
            prefs.update({
                'google_id': user_info.get('id'),
                'google_picture': user_info.get('picture', ''),
                'oauth_provider': 'google',
                'oauth_linked': True,
                'oauth_linked_at': datetime.utcnow().isoformat()
            })
            
            # Update profile image if not set
            if not current_user.profile_image and user_info.get('picture'):
                current_user.profile_image = user_info['picture']
            
            flash('Google account linked successfully', 'success')
        
        elif provider == 'apple':
            prefs.update({
                'apple_id': user_info.get('id'),
                'oauth_provider': 'apple',
                'oauth_linked': True,
                'oauth_linked_at': datetime.utcnow().isoformat()
            })
            
            flash('Apple account linked successfully', 'success')
        
        current_user.preferences = json.dumps(prefs)
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error linking OAuth account: {str(e)}")
        flash('Error linking OAuth account', 'danger')
    
    return redirect(url_for('auth.profile'))

@oauth_bp.route('/status')
@login_required
def oauth_status():
    """Get current user's OAuth status"""
    
    oauth_status = {
        'linked_accounts': [],
        'available_providers': list(oauth_manager.providers.keys())
    }
    
    if current_user.preferences:
        try:
            prefs = json.loads(current_user.preferences)
            
            if 'google_id' in prefs:
                oauth_status['linked_accounts'].append({
                    'provider': 'google',
                    'id': prefs['google_id'],
                    'picture': prefs.get('google_picture', ''),
                    'linked_at': prefs.get('oauth_linked_at', '')
                })
            
            if 'apple_id' in prefs:
                oauth_status['linked_accounts'].append({
                    'provider': 'apple',
                    'id': prefs['apple_id'],
                    'linked_at': prefs.get('oauth_linked_at', '')
                })
                
        except Exception as e:
            logger.error(f"Error getting OAuth status: {str(e)}")
    
    return jsonify(oauth_status)

@oauth_bp.route('/unlink-all')
@login_required
def unlink_all_oauth_accounts():
    """Unlink all OAuth accounts from current user"""
    
    if current_user.preferences:
        try:
            prefs = json.loads(current_user.preferences)
            
            # Remove OAuth-related fields
            oauth_fields = ['google_id', 'google_picture', 'apple_id', 'oauth_provider', 
                           'oauth_linked', 'oauth_linked_at', 'oauth_registration']
            
            for field in oauth_fields:
                if field in prefs:
                    del prefs[field]
            
            current_user.preferences = json.dumps(prefs)
            db.session.commit()
            
            flash('All OAuth accounts unlinked successfully', 'success')
            
        except Exception as e:
            logger.error(f"Error unlinking OAuth accounts: {str(e)}")
            flash('Error unlinking OAuth accounts', 'danger')
    
    return redirect(url_for('auth.profile'))
