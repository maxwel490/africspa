"""
Secure Model Extensions for Africa SPA System

Extends existing models with security features including:
- Automatic encryption/decryption
- Secure data access
- Audit logging
- Data validation
"""

import logging
from datetime import datetime
from sqlalchemy import event, inspect
from sqlalchemy.orm.attributes import flag_modified
from flask import current_app
from app.security.data_protection import data_protection
from app.security.database_security import db_security

logger = logging.getLogger(__name__)

class SecureModelMixin:
    """Mixin class to add security features to models"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._original_data = {}
        self._encrypted_fields = set()
    
    def encrypt_sensitive_fields(self):
        """Encrypt sensitive fields before saving"""
        try:
            model_class = self.__class__
            
            # Get sensitive fields for this model
            sensitive_fields = data_protection.sensitive_fields.get(model_class.__name__, [])
            
            for field in sensitive_fields:
                if hasattr(self, field):
                    value = getattr(self, field)
                    if value and not self._is_encrypted(value):
                        # Encrypt the field
                        encrypted_data = data_protection.encrypt_sensitive_data(
                            model_class, {field: value}
                        )
                        setattr(self, field, encrypted_data[field])
                        self._encrypted_fields.add(field)
            
        except Exception as e:
            logger.error(f"Error encrypting fields for {self.__class__.__name__}: {str(e)}")
    
    def decrypt_sensitive_fields(self):
        """Decrypt sensitive fields after loading"""
        try:
            model_class = self.__class__
            sensitive_fields = data_protection.sensitive_fields.get(model_class.__name__, [])
            
            for field in sensitive_fields:
                if hasattr(self, field):
                    value = getattr(self, field)
                    if value and self._is_encrypted(value):
                        # Decrypt the field
                        decrypted_data = data_protection.decrypt_sensitive_data(
                            model_class, {field: value}
                        )
                        setattr(self, field, decrypted_data[field])
            
        except Exception as e:
            logger.error(f"Error decrypting fields for {self.__class__.__name__}: {str(e)}")
    
    def _is_encrypted(self, value: str) -> bool:
        """Check if a value is already encrypted"""
        if not isinstance(value, str):
            return False
        
        # Check if it's base64 encoded (encrypted)
        try:
            import base64
            base64.b64decode(value)
            return True
        except Exception:
            return False
    
    def get_secure_dict(self, include_sensitive=False, mask_sensitive=True):
        """Get dictionary representation with security controls"""
        try:
            data = {}
            
            for column in self.__table__.columns.keys():
                value = getattr(self, column)
                
                if value is not None:
                    # Handle sensitive fields
                    if column in data_protection.masked_fields:
                        if include_sensitive and not mask_sensitive:
                            data[column] = value
                        elif mask_sensitive:
                            data[column] = data_protection.masked_fields[column](value)
                        else:
                            data[column] = '***'
                    else:
                        data[column] = value
            
            return data
            
        except Exception as e:
            logger.error(f"Error getting secure dict for {self.__class__.__name__}: {str(e)}")
            return {}
    
    def log_access(self, action: str, user_id: int = None):
        """Log access to this record"""
        try:
            db_security.log_security_event('model_access', {
                'action': action,
                'model': self.__class__.__name__,
                'record_id': getattr(self, 'id', None),
                'user_id': user_id,
                'ip': getattr(current_app, 'request', {}).remote_addr if hasattr(current_app, 'request') else None
            })
        except Exception as e:
            logger.error(f"Error logging access: {str(e)}")

def setup_model_events():
    """Setup SQLAlchemy events for model security"""
    try:
        @event.listens_for(SecureModelMixin, 'before_insert')
        def before_insert(mapper, connection, target):
            """Handle encryption before insert"""
            if isinstance(target, SecureModelMixin):
                target.encrypt_sensitive_fields()
                target.log_access('create')
        
        @event.listens_for(SecureModelMixin, 'before_update')
        def before_update(mapper, connection, target):
            """Handle encryption before update"""
            if isinstance(target, SecureModelMixin):
                # Check what changed
                changes = {}
                for attr in inspect(target).attrs:
                    if attr.key in target._original_data:
                        if getattr(target, attr.key) != target._original_data[attr.key]:
                            changes[attr.key] = {
                                'old': target._original_data[attr.key],
                                'new': getattr(target, attr.key)
                            }
                
                if changes:
                    target.encrypt_sensitive_fields()
                    target.log_access('update', changes=changes)
        
        # Note: after_load is not a valid SQLAlchemy event, 
        # we'll handle decryption in the model methods
        
    except Exception as e:
        logger.error(f"Error setting up model events: {str(e)}")

class SecureWorker(SecureModelMixin):
    """Secure extension for Worker model"""
    
    def get_secure_profile(self, viewer_role: str = None):
        """Get worker profile with role-based access control"""
        try:
            from app.models import Worker
            
            # Base profile data
            profile = {
                'id': self.id,
                'full_name': self.full_name,
                'role': self.role,
                'branch': self.branch,
                'specialty': getattr(self, 'specialty', None),
                'created_at': self.created_at,
                'is_active': self.is_active
            }
            
            # Add role-specific data
            if viewer_role == 'admin':
                # Admin can see most data except very sensitive info
                profile.update({
                    'username': self.username,
                    'phone': data_protection.mask_phone(self.phone) if self.phone else None,
                    'email': data_protection.mask_email(self.email) if self.email else None,
                    'base_salary': getattr(self, 'base_salary', 0)
                })
            elif viewer_role == 'accountant':
                # Accountant can see financial info
                profile.update({
                    'phone': data_protection.mask_phone(self.phone) if self.phone else None,
                    'base_salary': getattr(self, 'base_salary', 0),
                    'commission_rate': getattr(self, 'commission_rate', 0)
                })
            elif viewer_role == 'self' and hasattr(current_user, 'id') and current_user.id == self.id:
                # User can see their own full data
                profile.update({
                    'username': self.username,
                    'phone': self.phone,
                    'email': self.email,
                    'id_number': self.id_number,
                    'base_salary': getattr(self, 'base_salary', 0),
                    'commission_rate': getattr(self, 'commission_rate', 0)
                })
            
            return profile
            
        except Exception as e:
            logger.error(f"Error getting secure worker profile: {str(e)}")
            return {}
    
    def validate_sensitive_access(self, requesting_user):
        """Validate if user can access sensitive data"""
        try:
            # Admin can access all
            if requesting_user.role == 'admin':
                return True
            
            # Accountant can access financial data
            if requesting_user.role == 'accountant' and requesting_user.branch == self.branch:
                return True
            
            # User can access their own data
            if requesting_user.id == self.id:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error validating sensitive access: {str(e)}")
            return False

class SecureClient(SecureModelMixin):
    """Secure extension for Client model"""
    
    def get_secure_info(self, viewer_role: str = None):
        """Get client information with security controls"""
        try:
            info = {
                'id': self.id,
                'full_name': self.full_name,
                'created_at': self.created_at
            }
            
            # Add contact info based on role
            if viewer_role in ['admin', 'accountant']:
                info.update({
                    'phone': data_protection.mask_phone(self.phone) if self.phone else None,
                    'email': data_protection.mask_email(self.email) if self.email else None
                })
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting secure client info: {str(e)}")
            return {}

class SecureSalon(SecureModelMixin):
    """Secure extension for Salon model"""
    
    def get_secure_business_info(self, viewer_role: str = None):
        """Get salon business information with security controls"""
        try:
            info = {
                'id': self.id,
                'name': self.name,
                'slug': self.slug,
                'country': self.country,
                'is_active': self.is_active,
                'created_at': self.created_at
            }
            
            # Add sensitive info for authorized users
            if viewer_role == 'admin':
                info.update({
                    'email': data_protection.mask_email(self.email) if self.email else None,
                    'phone': data_protection.mask_phone(self.phone) if self.phone else None,
                    'max_branches': self.max_branches,
                    'max_staff': self.max_staff
                })
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting secure salon info: {str(e)}")
            return {}

# Initialize model events
try:
    setup_model_events()
except Exception as e:
    logger.error(f"Error setting up model events: {str(e)}")
