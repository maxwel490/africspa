#!/usr/bin/env python3
"""
Production Logging Configuration
Enhanced logging setup for production deployment
"""

import logging
import logging.handlers
import os
from datetime import datetime

def setup_production_logging(app):
    """
    Configure comprehensive logging for production
    """
    
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # File handlers
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # Main application log
    app_log_file = os.path.join(logs_dir, 'app.log')
    app_handler = logging.handlers.RotatingFileHandler(
        app_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    app_handler.setLevel(getattr(logging, log_level))
    
    # Error log
    error_log_file = os.path.join(logs_dir, 'error.log')
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    
    # Security log
    security_log_file = os.path.join(logs_dir, 'security.log')
    security_handler = logging.handlers.RotatingFileHandler(
        security_log_file,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=10
    )
    security_handler.setLevel(logging.INFO)
    
    # Audit log (JSON format)
    audit_log_file = os.path.join(logs_dir, 'audit.log')
    audit_handler = logging.handlers.RotatingFileHandler(
        audit_log_file,
        maxBytes=20*1024*1024,  # 20MB
        backupCount=10
    )
    audit_handler.setLevel(logging.INFO)
    
    # Formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
    )
    
    json_formatter = logging.Formatter(
        '%(asctime)s - %(message)s'
    )
    
    # Set formatters
    app_handler.setFormatter(detailed_formatter)
    error_handler.setFormatter(detailed_formatter)
    security_handler.setFormatter(detailed_formatter)
    audit_handler.setFormatter(json_formatter)
    
    # Add handlers to root logger
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)
    
    # Create specialized loggers
    security_logger = logging.getLogger('security')
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.INFO)
    security_logger.propagate = False
    
    audit_logger = logging.getLogger('audit')
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    
    # Configure Flask app logger
    app.logger.setLevel(getattr(logging, log_level))
    app.logger.addHandler(app_handler)
    
    # Configure SQLAlchemy logging
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
    
    # Configure Werkzeug logging
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    print(f"✓ Production logging configured at level: {log_level}")
    print(f"  - App log: {app_log_file}")
    print(f"  - Error log: {error_log_file}")
    print(f"  - Security log: {security_log_file}")
    print(f"  - Audit log: {audit_log_file}")
    
    return True

def log_security_event(event_type, user_id=None, details=None, ip_address=None):
    """
    Log security events for audit trail
    """
    security_logger = logging.getLogger('security')
    audit_logger = logging.getLogger('audit')
    
    timestamp = datetime.utcnow().isoformat()
    
    security_message = f"SECURITY_EVENT: {event_type}"
    if user_id:
        security_message += f" - User: {user_id}"
    if details:
        security_message += f" - Details: {details}"
    if ip_address:
        security_message += f" - IP: {ip_address}"
    
    security_logger.info(security_message)
    
    # Audit log (structured)
    audit_data = {
        'timestamp': timestamp,
        'event_type': event_type,
        'user_id': user_id,
        'details': details,
        'ip_address': ip_address
    }
    audit_logger.info(str(audit_data))

def setup_error_handlers(app):
    """
    Setup error handlers for production logging
    """
    
    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.warning(f"404 Not Found: {request.url}")
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"500 Internal Server Error: {error}")
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        app.logger.error(f"Unhandled exception: {error}", exc_info=True)
        return render_template('errors/500.html'), 500
    
    print("✓ Error handlers configured for production")
    return True
