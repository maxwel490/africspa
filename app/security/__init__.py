"""
Security Package Initialization for Africa SPA System

Configures and initializes all security components
"""

import logging
import os
from flask import current_app
from app.security.data_protection import data_protection
from app.security.database_security import db_security

logger = logging.getLogger(__name__)

def init_security(app):
    """Initialize all security components"""
    
    # Create necessary directories
    os.makedirs('logs', exist_ok=True)
    os.makedirs('backups', exist_ok=True)
    
    # Security configuration
    app.config.update({
        # Encryption settings
        'ENCRYPTION_KEY_FILE': '.encryption_key',
        
        # Logging settings
        'SECURITY_LOG_FILE': 'logs/security.log',
        'AUDIT_LOG_FILE': 'logs/audit.log',
        'LOG_ALL_QUERIES': app.config.get('ENV') == 'development',
        'SLOW_QUERY_THRESHOLD': 5.0,
        
        # Data protection settings
        'DATA_RETENTION_DAYS': 365,
        'BACKUP_ENCRYPTION': True,
        'AUTO_ANONYMIZATION': True,
        
        # Security headers
        'SECURITY_HEADERS': True,
        
        # Rate limiting
        'RATE_LIMIT_ENABLED': True,
        'RATE_LIMIT_PER_MINUTE': 60,
    })
    
    # Initialize database security
    db_security.init_app(app)
    
    # Set up logging
    setup_security_logging(app)
    
    logger.info("Security components initialized")

def setup_security_logging(app):
    """Setup security-specific logging"""
    
    # Security logger
    security_logger = logging.getLogger('security')
    security_logger.setLevel(logging.INFO)
    
    # Security file handler
    security_handler = logging.FileHandler(app.config.get('SECURITY_LOG_FILE', 'logs/security.log'))
    security_handler.setLevel(logging.INFO)
    
    # Security formatter
    security_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    security_handler.setFormatter(security_formatter)
    
    security_logger.addHandler(security_handler)
    
    # Audit logger
    audit_logger = logging.getLogger('audit')
    audit_logger.setLevel(logging.INFO)
    
    # Audit file handler
    audit_handler = logging.FileHandler(app.config.get('AUDIT_LOG_FILE', 'logs/audit.log'))
    audit_handler.setLevel(logging.INFO)
    
    # Audit formatter (JSON-like)
    audit_formatter = logging.Formatter('%(message)s')
    audit_handler.setFormatter(audit_formatter)
    
    audit_logger.addHandler(audit_handler)

# Export main components
from app.security.data_protection import DataProtectionService, data_protection
from app.security.database_security import DatabaseSecurityMiddleware, db_security, protect_sensitive_data, prevent_sql_injection
from app.security.secure_models import SecureModelMixin, SecureWorker, SecureClient, SecureSalon

__all__ = [
    'init_security',
    'data_protection',
    'db_security',
    'protect_sensitive_data',
    'prevent_sql_injection',
    'SecureModelMixin',
    'SecureWorker',
    'SecureClient',
    'SecureSalon'
]
