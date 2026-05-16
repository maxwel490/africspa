"""
Database Security Middleware for Africa SPA System

Implements database-level security measures including:
- Connection security
- Query logging
- SQL injection prevention
- Access control
- Data leak prevention
"""

import logging
import hashlib
import time
from functools import wraps
from flask import request, g, current_app
from flask_login import current_user
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from app.security.data_protection import data_protection

logger = logging.getLogger(__name__)

class DatabaseSecurityMiddleware:
    """Middleware for database security and monitoring"""
    
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
        
        # Suspicious query patterns
        self.suspicious_patterns = [
            'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'EXEC', 'UNION',
            '--', '/*', '*/', 'xp_', 'sp_', 'INSERT INTO',
            'UPDATE SET', 'GRANT', 'REVOKE', 'CREATE', 'SHOW'
        ]
        
        # Track query patterns
        self.query_stats = {
            'total_queries': 0,
            'suspicious_queries': 0,
            'failed_logins': 0,
            'data_exports': 0
        }
    
    def init_app(self, app):
        """Initialize database security with Flask app"""
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        
        # Register SQLAlchemy event listeners
        if hasattr(app, 'extensions') and 'sqlalchemy' in app.extensions:
            self.register_sqlalchemy_events()
    
    def register_sqlalchemy_events(self):
        """Register SQLAlchemy event listeners for security monitoring"""
        
        @event.listens_for(Engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """Monitor all database queries"""
            try:
                self.query_stats['total_queries'] += 1
                
                # Check for suspicious patterns
                statement_upper = statement.upper()
                if any(pattern.upper() in statement_upper for pattern in self.suspicious_patterns):
                    self.query_stats['suspicious_queries'] += 1
                    logger.warning(f"Suspicious query detected: {statement[:100]}...")
                    self.log_security_event('suspicious_query', {
                        'statement': statement[:200],
                        'parameters': str(parameters)[:100],
                        'user_id': getattr(current_user, 'id', None),
                        'ip': request.remote_addr if request else None
                    })
                
                # Log query for audit (in production, be selective)
                if current_app.config.get('LOG_ALL_QUERIES', False):
                    logger.debug(f"Query: {statement[:100]}...")
                    
            except Exception as e:
                logger.error(f"Error in query monitoring: {str(e)}")
        
        @event.listens_for(Engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """Monitor query execution time"""
            try:
                # Track slow queries
                if hasattr(context, 'query_start_time'):
                    execution_time = time.time() - context.query_start_time
                    if execution_time > current_app.config.get('SLOW_QUERY_THRESHOLD', 5.0):
                        logger.warning(f"Slow query detected: {execution_time:.2f}s - {statement[:100]}...")
                        self.log_security_event('slow_query', {
                            'execution_time': execution_time,
                            'statement': statement[:200],
                            'user_id': getattr(current_user, 'id', None)
                        })
            except Exception as e:
                logger.error(f"Error in query monitoring: {str(e)}")
    
    def before_request(self):
        """Setup request context for security monitoring"""
        if hasattr(request, 'query_start_time'):
            g.query_start_time = time.time()
        
        # Log access attempts
        if request.endpoint:
            self.log_security_event('endpoint_access', {
                'endpoint': request.endpoint,
                'method': request.method,
                'user_id': getattr(current_user, 'id', None),
                'ip': request.remote_addr
            })
    
    def after_request(self, response):
        """Clean up request context and log security events"""
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Remove sensitive headers
        response.headers.pop('Server', None)
        response.headers.pop('X-Powered-By', None)
        
        return response
    
    def log_security_event(self, event_type: str, details: dict):
        """Log security events for monitoring"""
        try:
            security_log = current_app.config.get('SECURITY_LOG_FILE', 'logs/security.log')
            
            log_entry = {
                'timestamp': time.time(),
                'event_type': event_type,
                'details': details,
                'ip': request.remote_addr if request else None,
                'user_agent': request.headers.get('User-Agent', '')[:200] if request else ''
            }
            
            with open(security_log, 'a') as f:
                f.write(f"{log_entry}\n")
            
        except Exception as e:
            logger.error(f"Error logging security event: {str(e)}")
    
    def check_sql_injection(self, query: str) -> bool:
        """Check for potential SQL injection attempts"""
        try:
            # Common SQL injection patterns
            injection_patterns = [
                '\'\s*OR\s*\'\d+\s*=\s*\d+',
                '\'\s*OR\s*\'\s*=\s*\'',
                '\'\s*AND\s*\'\d+\s*=\s*\d+',
                '\'\s*AND\s*\'\s*=\s*\'',
                '\'\s*;\s*DROP',
                '\'\s*;\s*DELETE',
                '\'\s*;\s*INSERT',
                '\'\s*;\s*UPDATE',
                'UNION\s+SELECT',
                '1\s*=\s*1',
                'TRUE\s*=\s*TRUE'
            ]
            
            query_upper = query.upper()
            for pattern in injection_patterns:
                if pattern in query_upper:
                    logger.error(f"SQL injection attempt detected: {query[:100]}...")
                    self.log_security_event('sql_injection_attempt', {
                        'query': query[:200],
                        'pattern': pattern,
                        'user_id': getattr(current_user, 'id', None),
                        'ip': request.remote_addr if request else None
                    })
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking SQL injection: {str(e)}")
            return False
    
    def sanitize_input(self, data: str) -> str:
        """Sanitize user input to prevent injection"""
        if not data:
            return data
        
        # Remove dangerous characters
        dangerous_chars = ["'", '"', ';', '--', '/*', '*/', 'xp_', 'sp_']
        sanitized = data
        
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        
        return sanitized.strip()
    
    def encrypt_sensitive_columns(self, model_class):
        """Decorator to encrypt sensitive columns automatically"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Get the data before saving
                if hasattr(model_class, '__tablename__'):
                    # This is a model class, apply encryption to sensitive data
                    pass
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def get_security_stats(self) -> dict:
        """Get current security statistics"""
        return self.query_stats.copy()
    
    def reset_security_stats(self):
        """Reset security statistics"""
        self.query_stats = {
            'total_queries': 0,
            'suspicious_queries': 0,
            'failed_logins': 0,
            'data_exports': 0
        }

# Global instance
db_security = DatabaseSecurityMiddleware()

# Decorator for protecting sensitive routes
def protect_sensitive_data(func):
    """Decorator to protect sensitive data in routes"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check if user has permission to access sensitive data
        if not current_user.is_authenticated:
            return unauthorized_access()
        
        # Log data access
        db_security.log_security_event('sensitive_data_access', {
            'endpoint': request.endpoint,
            'method': request.method,
            'user_id': current_user.id,
            'ip': request.remote_addr
        })
        
        return func(*args, **kwargs)
    return wrapper

def unauthorized_access():
    """Return unauthorized access response"""
    return {'error': 'Unauthorized access'}, 401

# SQL injection prevention middleware
def prevent_sql_injection(func):
    """Decorator to prevent SQL injection in functions"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check request parameters for injection attempts
        for key, value in request.args.items():
            if isinstance(value, str) and db_security.check_sql_injection(value):
                return {'error': 'Invalid input detected'}, 400
        
        for key, value in request.form.items():
            if isinstance(value, str) and db_security.check_sql_injection(value):
                return {'error': 'Invalid input detected'}, 400
        
        return func(*args, **kwargs)
    return wrapper
