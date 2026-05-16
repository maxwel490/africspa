"""
OAuth Providers for Africa SPA System

Supports Google and Apple (iCloud) OAuth authentication
"""

import json
import requests
from flask import request, redirect, url_for, flash, session
from flask_login import login_user
from app.models import Worker, db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class OAuthProvider:
    """Base class for OAuth providers"""
    
    def __init__(self, name, client_id, client_secret, redirect_uri):
        self.name = name
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
    
    def get_authorization_url(self):
        """Get the authorization URL for OAuth flow"""
        raise NotImplementedError
    
    def get_access_token(self, code):
        """Exchange authorization code for access token"""
        raise NotImplementedError
    
    def get_user_info(self, access_token):
        """Get user information from OAuth provider"""
        raise NotImplementedError
    
    def authenticate_user(self, user_info):
        """Authenticate or create user based on OAuth info"""
        raise NotImplementedError

class GoogleOAuthProvider(OAuthProvider):
    """Google OAuth 2.0 Provider"""
    
    def __init__(self, client_id, client_secret, redirect_uri):
        super().__init__('google', client_id, client_secret, redirect_uri)
        self.auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
        self.userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        self.scope = "openid email profile"
    
    def get_authorization_url(self):
        """Get Google OAuth authorization URL"""
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': self.scope,
            'response_type': 'code',
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        param_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"{self.auth_url}?{param_string}"
    
    def get_access_token(self, code):
        """Exchange authorization code for access token"""
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri
        }
        
        response = requests.post(self.token_url, data=data)
        
        if response.status_code != 200:
            logger.error(f"Google OAuth token error: {response.text}")
            return None
        
        return response.json()
    
    def get_user_info(self, access_token):
        """Get user information from Google"""
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(self.userinfo_url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Google OAuth userinfo error: {response.text}")
            return None
        
        return response.json()
    
    def authenticate_user(self, user_info):
        """Authenticate or create user based on Google OAuth info"""
        email = user_info.get('email')
        google_id = user_info.get('id')
        name = user_info.get('name', '')
        picture = user_info.get('picture', '')
        
        if not email:
            logger.error("Google OAuth: No email provided")
            return None, "No email provided by Google"
        
        # Find existing user by email or Google ID
        user = Worker.query.filter(
            (Worker.email == email) | 
            (Worker.username == email)
        ).first()
        
        if not user:
            # Check if there's a user with Google ID stored in preferences
            users = Worker.query.all()
            for u in users:
                if u.preferences:
                    try:
                        prefs = json.loads(u.preferences)
                        if prefs.get('google_id') == google_id:
                            user = u
                            break
                    except:
                        continue
        
        if user:
            # Update user's Google OAuth info
            if not user.preferences:
                user.preferences = json.dumps({})
            
            prefs = json.loads(user.preferences)
            prefs.update({
                'google_id': google_id,
                'google_picture': picture,
                'oauth_provider': 'google',
                'last_oauth_login': datetime.utcnow().isoformat()
            })
            user.preferences = json.dumps(prefs)
            
            # Update profile image if not set
            if not user.profile_image and picture:
                user.profile_image = picture
            
            # Update email if different
            if not user.email or user.email != email:
                user.email = email
            
            # Update name if not set
            if not user.full_name or user.full_name == '':
                user.full_name = name
            
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Google OAuth: Existing user logged in - {email}")
            return user, None
        else:
            # Create new user (need to determine role and salon)
            # For OAuth users, we'll create them as inactive and require admin approval
            username = email.split('@')[0]
            
            # Check if username exists
            existing_user = Worker.query.filter_by(username=username).first()
            if existing_user:
                username = f"{username}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            
            new_user = Worker(
                username=username,
                email=email,
                full_name=name,
                role='pending',  # Requires admin approval
                is_active=False,  # Inactive until approved
                profile_image=picture,
                preferences=json.dumps({
                    'google_id': google_id,
                    'google_picture': picture,
                    'oauth_provider': 'google',
                    'oauth_registration': datetime.utcnow().isoformat()
                })
            )
            
            # Set a temporary password (won't be used for OAuth)
            temp_password = f"oauth_{google_id}_{datetime.utcnow().timestamp()}"
            new_user.set_password(temp_password)
            
            db.session.add(new_user)
            db.session.commit()
            
            logger.info(f"Google OAuth: New user created - {email}")
            flash('Your account has been created but requires admin approval. Please contact your administrator.', 'warning')
            return None, "Account created but requires admin approval"

class AppleOAuthProvider(OAuthProvider):
    """Apple Sign In Provider (iCloud)"""
    
    def __init__(self, client_id, client_secret, redirect_uri):
        super().__init__('apple', client_id, client_secret, redirect_uri)
        self.auth_url = "https://appleid.apple.com/auth/authorize"
        self.token_url = "https://appleid.apple.com/auth/token"
        self.scope = "name email"
    
    def get_authorization_url(self):
        """Get Apple Sign In authorization URL"""
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': self.scope,
            'response_type': 'code',
            'response_mode': 'form_post',
            'state': self._generate_state()
        }
        
        param_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"{self.auth_url}?{param_string}"
    
    def _generate_state(self):
        """Generate state parameter for CSRF protection"""
        import secrets
        return secrets.token_urlsafe(32)
    
    def get_access_token(self, code):
        """Exchange authorization code for access token"""
        import jwt
        import time
        
        # Create client secret JWT
        now = int(time.time())
        payload = {
            'iss': self.client_id,
            'iat': now,
            'exp': now + 3600,  # 1 hour expiration
            'aud': 'https://appleid.apple.com',
            'sub': self.client_id
        }
        
        # Note: This requires the private key file from Apple Developer Console
        # For now, we'll use a simplified approach
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri
        }
        
        response = requests.post(self.token_url, data=data)
        
        if response.status_code != 200:
            logger.error(f"Apple OAuth token error: {response.text}")
            return None
        
        return response.json()
    
    def get_user_info(self, access_token):
        """Get user information from Apple (from ID token)"""
        # Apple returns user info in the ID token
        # This is a simplified version - in production, you'd decode the JWT
        return {}
    
    def authenticate_user(self, user_info):
        """Authenticate or create user based on Apple Sign In info"""
        # Apple Sign In implementation would go here
        # For now, return not implemented
        return None, "Apple Sign In not fully implemented yet"

class OAuthManager:
    """Manages OAuth providers and authentication"""
    
    def __init__(self):
        self.providers = {}
        self._init_providers()
    
    def _init_providers(self):
        """Initialize OAuth providers"""
        # Note: This will be initialized later when app context is available
        pass
    
    def init_providers(self, app):
        """Initialize OAuth providers with app context"""
        from flask import current_app
        
        # Google OAuth
        google_client_id = current_app.config.get('GOOGLE_CLIENT_ID')
        google_client_secret = current_app.config.get('GOOGLE_CLIENT_SECRET')
        google_redirect_uri = current_app.config.get('GOOGLE_REDIRECT_URI', 
            f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/oauth/google/callback")
        
        if google_client_id and google_client_secret:
            self.providers['google'] = GoogleOAuthProvider(
                google_client_id, google_client_secret, google_redirect_uri
            )
        
        # Apple Sign In
        apple_client_id = current_app.config.get('APPLE_CLIENT_ID')
        apple_client_secret = current_app.config.get('APPLE_CLIENT_SECRET')
        apple_redirect_uri = current_app.config.get('APPLE_REDIRECT_URI',
            f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/oauth/apple/callback")
        
        if apple_client_id and apple_client_secret:
            self.providers['apple'] = AppleOAuthProvider(
                apple_client_id, apple_client_secret, apple_redirect_uri
            )
    
    def get_provider(self, provider_name):
        """Get OAuth provider by name"""
        return self.providers.get(provider_name)
    
    def handle_oauth_callback(self, provider_name, code=None, error=None):
        """Handle OAuth callback"""
        if error:
            logger.error(f"OAuth callback error for {provider_name}: {error}")
            return None, f"OAuth authentication failed: {error}"
        
        provider = self.get_provider(provider_name)
        if not provider:
            return None, f"OAuth provider {provider_name} not configured"
        
        try:
            # Exchange code for access token
            token_data = provider.get_access_token(code)
            if not token_data:
                return None, "Failed to get access token"
            
            access_token = token_data.get('access_token')
            if not access_token:
                return None, "No access token received"
            
            # Get user information
            user_info = provider.get_user_info(access_token)
            if not user_info:
                return None, "Failed to get user information"
            
            # Authenticate user
            user, message = provider.authenticate_user(user_info)
            
            if user and user.is_active:
                login_user(user)
                logger.info(f"OAuth login successful: {provider_name} - {user.email}")
                return user, None
            elif user and not user.is_active:
                return user, "Account is inactive. Please contact administrator."
            else:
                return None, message or "Authentication failed"
                
        except Exception as e:
            logger.error(f"OAuth callback error for {provider_name}: {str(e)}")
            return None, f"Authentication error: {str(e)}"

# Global OAuth manager instance
oauth_manager = OAuthManager()
