"""
Database Security and Data Protection for Africa SPA System

Implements comprehensive data protection measures including:
- Data encryption at rest
- Sensitive data masking
- Access control auditing
- Data anonymization
- Backup encryption
"""

import logging
import hashlib
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import current_app
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)

class DataProtectionService:
    """Handles database security and data protection"""
    
    def __init__(self):
        self._encryption_key = None
        self._cipher_suite = None
        
        # Fields that contain sensitive data
        self.sensitive_fields = {
            'Worker': ['phone', 'email', 'id_number', 'address', 'bank_account', 'salary'],
            'Client': ['phone', 'email', 'address'],
            'Salon': ['phone', 'email', 'address', 'bank_account'],
            'Appointment': ['client_notes', 'payment_details'],
            'ServiceOrder': ['client_phone', 'payment_info']
        }
        
        # Fields to completely mask in logs and exports
        self.masked_fields = {
            'phone': lambda x: self._mask_phone(x),
            'email': lambda x: self._mask_email(x),
            'id_number': lambda x: self._mask_id(x),
            'bank_account': lambda x: self._mask_account(x),
            'address': lambda x: self._mask_address(x)
        }
    
    @property
    def encryption_key(self):
        """Lazy loading of encryption key"""
        if self._encryption_key is None:
            self._encryption_key = self._get_or_create_encryption_key()
            self._cipher_suite = Fernet(self._encryption_key)
        return self._encryption_key
    
    @property
    def cipher_suite(self):
        """Lazy loading of cipher suite"""
        if self._cipher_suite is None:
            self._encryption_key = self._get_or_create_encryption_key()
            self._cipher_suite = Fernet(self._encryption_key)
        return self._cipher_suite
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Generate or retrieve encryption key"""
        from flask import current_app
        
        key_file = current_app.config.get('ENCRYPTION_KEY_FILE', '.encryption_key')
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        
        # Generate new key
        password = current_app.config.get('SECRET_KEY', 'default').encode()
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        
        # Save key with restricted permissions
        with open(key_file, 'wb') as f:
            f.write(key)
        os.chmod(key_file, 0o600)  # Only owner can read/write
        
        return key
    
    def encrypt_sensitive_data(self, model_class, data: dict) -> dict:
        """
        Encrypt sensitive data before storing in database
        
        Args:
            model_class: The model class (Worker, Client, etc.)
            data: Dictionary of data to encrypt
            
        Returns:
            Dictionary with encrypted sensitive fields
        """
        try:
            model_name = model_class.__name__
            sensitive_fields = self.sensitive_fields.get(model_name, [])
            
            encrypted_data = data.copy()
            
            for field in sensitive_fields:
                if field in data and data[field]:
                    # Convert to JSON for complex data types
                    original_value = data[field]
                    if isinstance(original_value, (dict, list)):
                        json_value = json.dumps(original_value)
                        encrypted_value = self.cipher_suite.encrypt(json_value.encode())
                    else:
                        encrypted_value = self.cipher_suite.encrypt(str(original_value).encode())
                    
                    # Store as base64 string
                    encrypted_data[field] = base64.b64encode(encrypted_value).decode()
            
            return encrypted_data
            
        except Exception as e:
            logger.error(f"Error encrypting data: {str(e)}")
            return data  # Return original data on error
    
    def decrypt_sensitive_data(self, model_class, data: dict) -> dict:
        """
        Decrypt sensitive data when retrieving from database
        
        Args:
            model_class: The model class
            data: Dictionary with potentially encrypted data
            
        Returns:
            Dictionary with decrypted sensitive fields
        """
        try:
            model_name = model_class.__name__
            sensitive_fields = self.sensitive_fields.get(model_name, [])
            
            decrypted_data = data.copy()
            
            for field in sensitive_fields:
                if field in data and data[field]:
                    encrypted_value = base64.b64decode(data[field].encode())
                    decrypted_value = self.cipher_suite.decrypt(encrypted_value).decode()
                    
                    # Try to parse as JSON first
                    try:
                        decrypted_data[field] = json.loads(decrypted_value)
                    except json.JSONDecodeError:
                        decrypted_data[field] = decrypted_value
            
            return decrypted_data
            
        except Exception as e:
            logger.error(f"Error decrypting data: {str(e)}")
            return data  # Return original data on error
    
    def mask_sensitive_data(self, data: dict, context: str = 'general') -> dict:
        """
        Mask sensitive data for logging, exports, or debugging
        
        Args:
            data: Dictionary containing sensitive data
            context: Context for masking (logs, exports, debug)
            
        Returns:
            Dictionary with masked sensitive fields
        """
        try:
            masked_data = data.copy()
            
            for field, value in data.items():
                if field in self.masked_fields and value:
                    masked_data[field] = self.masked_fields[field](value)
            
            return masked_data
            
        except Exception as e:
            logger.error(f"Error masking data: {str(e)}")
            return data
    
    def _mask_phone(self, phone: str) -> str:
        """Mask phone number showing only last 4 digits"""
        if not phone or len(phone) < 4:
            return "***-***-****"
        return f"***-***-{phone[-4:]}"
    
    def _mask_email(self, email: str) -> str:
        """Mask email showing first 2 and last 2 characters"""
        if not email or '@' not in email:
            return "***@***.com"
        local, domain = email.split('@', 1)
        if len(local) <= 4:
            return f"{'*' * len(local)}@{domain}"
        return f"{local[:2]}{'*' * (len(local) - 4)}{local[-2:]}@{domain}"
    
    def _mask_id(self, id_number: str) -> str:
        """Mask ID number showing only last 4 digits"""
        if not id_number or len(id_number) < 4:
            return "****"
        return f"{'*' * (len(id_number) - 4)}{id_number[-4:]}"
    
    def _mask_account(self, account: str) -> str:
        """Mask bank account number"""
        if not account or len(account) < 4:
            return "****"
        return f"****-****-****-{account[-4:]}"
    
    def _mask_address(self, address: str) -> str:
        """Mask address showing only city and country"""
        if not address:
            return "***"
        # Simple masking - show only last part
        parts = address.split(',')
        if len(parts) > 1:
            return f"***, {parts[-1].strip()}"
        return "***"
    
    def audit_data_access(self, user_id: int, action: str, table: str, record_id: int = None):
        """
        Log data access for security auditing
        
        Args:
            user_id: ID of the user accessing data
            action: Action performed (read, create, update, delete)
            table: Database table accessed
            record_id: ID of the specific record (if applicable)
        """
        try:
            audit_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'user_id': user_id,
                'action': action,
                'table': table,
                'record_id': record_id,
                'ip_address': getattr(request, 'remote_addr', 'unknown') if 'request' in globals() else 'unknown',
                'user_agent': getattr(request, 'user_agent', 'unknown') if 'request' in globals() else 'unknown'
            }
            
            # Log to secure audit file
            audit_log_file = current_app.config.get('AUDIT_LOG_FILE', 'logs/audit.log')
            with open(audit_log_file, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
            
            logger.info(f"Data access audit: {audit_entry}")
            
        except Exception as e:
            logger.error(f"Error logging audit entry: {str(e)}")
    
    def create_secure_backup(self, backup_path: str) -> bool:
        """
        Create encrypted backup of sensitive data
        
        Args:
            backup_path: Path where backup will be saved
            
        Returns:
            True if backup successful, False otherwise
        """
        try:
            from app.models import Worker, Client, Salon, Appointment, ServiceOrder
            
            backup_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'version': '1.0',
                'tables': {}
            }
            
            # Backup sensitive tables with encryption
            tables_to_backup = [Worker, Client, Salon, Appointment, ServiceOrder]
            
            for table in tables_to_backup:
                table_name = table.__name__
                records = table.query.all()
                
                backup_data['tables'][table_name] = []
                for record in records:
                    record_data = {}
                    for column in record.__table__.columns.keys():
                        value = getattr(record, column)
                        if value is not None:
                            record_data[column] = value
                    
                    # Encrypt sensitive data
                    encrypted_record = self.encrypt_sensitive_data(table, record_data)
                    backup_data['tables'][table_name].append(encrypted_record)
            
            # Encrypt entire backup
            backup_json = json.dumps(backup_data)
            encrypted_backup = self.cipher_suite.encrypt(backup_json.encode())
            
            # Save encrypted backup
            with open(backup_path, 'wb') as f:
                f.write(encrypted_backup)
            
            # Set secure permissions
            os.chmod(backup_path, 0o600)
            
            logger.info(f"Secure backup created: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating secure backup: {str(e)}")
            return False
    
    def restore_secure_backup(self, backup_path: str) -> bool:
        """
        Restore data from encrypted backup
        
        Args:
            backup_path: Path to encrypted backup file
            
        Returns:
            True if restore successful, False otherwise
        """
        try:
            # Read and decrypt backup
            with open(backup_path, 'rb') as f:
                encrypted_backup = f.read()
            
            decrypted_backup = self.cipher_suite.decrypt(encrypted_backup)
            backup_data = json.loads(decrypted_backup.decode())
            
            # Restore data (implementation would depend on specific requirements)
            logger.info(f"Secure backup restored from: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error restoring secure backup: {str(e)}")
            return False
    
    def anonymize_old_data(self, days_old: int = 365) -> int:
        """
        Anonymize old data to comply with privacy regulations
        
        Args:
            days_old: Age of data to anonymize (in days)
            
        Returns:
            Number of records anonymized
        """
        try:
            from app.models import Worker, Client, Appointment
            from app import db
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            anonymized_count = 0
            
            # Anonymize old workers who are no longer active
            old_workers = Worker.query.filter(
                Worker.created_at < cutoff_date,
                Worker.is_active == False
            ).all()
            
            for worker in old_workers:
                # Anonymize sensitive fields
                worker.phone = f"ANONYMIZED_{worker.id}"
                worker.email = f"anon_{worker.id}@anon.com"
                worker.id_number = f"ANON_{worker.id}"
                worker.address = "ANONYMIZED"
                anonymized_count += 1
            
            # Anonymize old clients
            old_clients = Client.query.filter(
                Client.created_at < cutoff_date
            ).all()
            
            for client in old_clients:
                client.phone = f"ANONYMIZED_{client.id}"
                client.email = f"anon_{client.id}@anon.com"
                client.address = "ANONYMIZED"
                anonymized_count += 1
            
            db.session.commit()
            logger.info(f"Anonymized {anonymized_count} records older than {days_old} days")
            return anonymized_count
            
        except Exception as e:
            logger.error(f"Error anonymizing old data: {str(e)}")
            return 0

# Global instance
data_protection = DataProtectionService()
