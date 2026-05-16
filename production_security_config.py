#!/usr/bin/env python3
"""
Production Security Configuration
Enhanced security settings for production deployment
"""

from flask_talisman import Talisman

def configure_production_security(app):
    """
    Configure enhanced security headers and policies for production
    """
    
    # Content Security Policy for production
    csp = {
        'default-src': "'self'",
        'script-src': [
            "'self'",
            "'unsafe-inline'",  # Required for Bootstrap/JS libraries
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com',
            'https://www.google.com',
            'https://www.gstatic.com'
        ],
        'style-src': [
            "'self'",
            "'unsafe-inline'",  # Required for Bootstrap/Font Awesome
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com',
            'https://fonts.googleapis.com'
        ],
        'font-src': [
            "'self'",
            'https://cdnjs.cloudflare.com',
            'https://fonts.gstatic.com'
        ],
        'img-src': [
            "'self'",
            'data:',
            'https:',
            'http:'
        ],
        'connect-src': [
            "'self'",
            'https://www.google.com',
            'https://accounts.google.com'
        ],
        'frame-src': "'self'",
        'object-src': "'none'",
        'media-src': "'self'",
        'manifest-src': "'self'"
    }
    
    # Feature Policy
    feature_policy = {
        'geolocation': "'none'",
        'camera': "'none'",
        'microphone': "'none'",
        'payment': "'none'",
        'usb': "'none'",
        'magnetometer': "'none'",
        'gyroscope': "'none'",
        'accelerometer': "'none'"
    }
    
    # Initialize Talisman with production security settings
    Talisman(
        app,
        force_https=app.config.get('FORCE_HTTPS', True),
        strict_transport_security=True,
        strict_transport_security_preload=True,
        strict_transport_security_max_age=31536000,
        content_security_policy=csp,
        feature_policy=feature_policy,
        referrer_policy='strict-origin-when-cross-origin',
        permissions_policy=feature_policy,
        # Additional security headers
        x_content_type_options=True,
        x_frame_options='DENY',
        x_xss_protection=True,
        # Allow specific domains for OAuth
        force_https_exclude_routes=[
            '/oauth/google/callback',
            '/oauth/apple/callback'
        ]
    )
    
    print("✓ Production security configuration applied")
    return True

def validate_security_config(app):
    """
    Validate that security requirements are met for production
    """
    errors = []
    warnings = []
    
    # Check critical security settings
    if not app.config.get('SECRET_KEY') or app.config['SECRET_KEY'] == 'africspa-production-fallback-key':
        errors.append("SECRET_KEY must be set to a strong, unique value in production")
    
    if not app.config.get('FORCE_HTTPS', False):
        errors.append("FORCE_HTTPS must be enabled in production")
    
    if app.config.get('DEBUG', False):
        errors.append("DEBUG mode must be disabled in production")
    
    # Check OAuth settings
    if not app.config.get('GOOGLE_CLIENT_ID'):
        warnings.append("Google OAuth not configured")
    
    if not app.config.get('APPLE_CLIENT_ID'):
        warnings.append("Apple OAuth not configured")
    
    # Database security
    if 'localhost' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
        warnings.append("Using localhost database - ensure this is intended for production")
    
    # Report results
    if errors:
        print("✗ Security Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
    
    if warnings:
        print("⚠ Security Configuration Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    
    if not errors and not warnings:
        print("✓ Security configuration validated successfully")
    
    return len(errors) == 0
