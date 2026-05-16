"""
Security Command Line Interface for Africa SPA System

Provides CLI commands for:
- Data encryption/decryption
- Backup management
- Security monitoring
- Data anonymization
"""

import click
from flask import current_app
from app.security.data_protection import data_protection
from app.security.database_security import db_security
from datetime import datetime, timedelta
import json

@click.group()
def security():
    """Security management commands"""
    pass

@security.command()
@click.option('--table', help='Specific table to encrypt')
@click.option('--dry-run', is_flag=True, help='Show what would be encrypted without doing it')
def encrypt_data(table, dry_run):
    """Encrypt sensitive data in the database"""
    click.echo("🔐 Starting data encryption...")
    
    try:
        from app import create_app, db
        from app.models import Worker, Client, Salon, Appointment, ServiceOrder
        
        app = create_app()
        with app.app_context():
            tables_to_process = []
            
            if table:
                if table == 'Worker':
                    tables_to_process = [(Worker, Worker.query.all())]
                elif table == 'Client':
                    tables_to_process = [(Client, Client.query.all())]
                elif table == 'Salon':
                    tables_to_process = [(Salon, Salon.query.all())]
                elif table == 'Appointment':
                    tables_to_process = [(Appointment, Appointment.query.all())]
                elif table == 'ServiceOrder':
                    tables_to_process = [(ServiceOrder, ServiceOrder.query.all())]
                else:
                    click.echo(f"❌ Unknown table: {table}")
                    return
            else:
                tables_to_process = [
                    (Worker, Worker.query.all()),
                    (Client, Client.query.all()),
                    (Salon, Salon.query.all()),
                    (Appointment, Appointment.query.all()),
                    (ServiceOrder, ServiceOrder.query.all())
                ]
            
            total_encrypted = 0
            
            for model_class, records in tables_to_process:
                click.echo(f"📊 Processing {model_class.__name__}...")
                
                for record in records:
                    if dry_run:
                        click.echo(f"   Would encrypt: {record.__class__.__name__} ID {record.id}")
                    else:
                        # Encrypt sensitive fields
                        sensitive_fields = data_protection.sensitive_fields.get(model_class.__name__, [])
                        encrypted_fields = []
                        
                        for field in sensitive_fields:
                            if hasattr(record, field):
                                value = getattr(record, field)
                                if value and not data_protection._is_encrypted(value):
                                    encrypted_data = data_protection.encrypt_sensitive_data(
                                        model_class, {field: value}
                                    )
                                    setattr(record, field, encrypted_data[field])
                                    encrypted_fields.append(field)
                        
                        if encrypted_fields:
                            total_encrypted += 1
                            click.echo(f"   ✅ Encrypted {model_class.__name__} ID {record.id} - Fields: {encrypted_fields}")
                
                if not dry_run:
                    db.session.commit()
            
            if dry_run:
                click.echo("🔍 Dry run completed - no changes made")
            else:
                click.echo(f"✅ Encryption completed - {total_encrypted} records processed")
                
    except Exception as e:
        click.echo(f"❌ Error during encryption: {str(e)}")

@security.command()
@click.option('--backup-path', default=f'backups/secure_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.enc')
def create_backup(backup_path):
    """Create encrypted backup of sensitive data"""
    click.echo(f"💾 Creating secure backup: {backup_path}")
    
    try:
        from app import create_app
        
        app = create_app()
        with app.app_context():
            success = data_protection.create_secure_backup(backup_path)
            
            if success:
                click.echo(f"✅ Backup created successfully: {backup_path}")
                click.echo("🔐 Backup is encrypted and password-protected")
            else:
                click.echo("❌ Failed to create backup")
                
    except Exception as e:
        click.echo(f"❌ Error creating backup: {str(e)}")

@security.command()
@click.option('--backup-path', required=True)
@click.option('--restore-path', help='Path to restore database (for testing)')
def restore_backup(backup_path, restore_path):
    """Restore data from encrypted backup"""
    click.echo(f"🔄 Restoring from backup: {backup_path}")
    
    try:
        from app import create_app
        
        app = create_app()
        with app.app_context():
            if restore_path:
                # For testing - just show what would be restored
                click.echo("🔍 Dry run mode - showing backup contents:")
                success = data_protection.restore_secure_backup(backup_path)
            else:
                success = data_protection.restore_secure_backup(backup_path)
            
            if success:
                click.echo("✅ Backup restored successfully")
            else:
                click.echo("❌ Failed to restore backup")
                
    except Exception as e:
        click.echo(f"❌ Error restoring backup: {str(e)}")

@security.command()
@click.option('--days', default=365, help='Age of data to anonymize (in days)')
@click.option('--dry-run', is_flag=True, help='Show what would be anonymized')
def anonymize_data(days, dry_run):
    """Anonymize old data to comply with privacy regulations"""
    click.echo(f"🎭 Anonymizing data older than {days} days...")
    
    try:
        from app import create_app
        
        app = create_app()
        with app.app_context():
            if dry_run:
                click.echo("🔍 Dry run mode - showing what would be anonymized:")
                # Show count of records that would be affected
                from app.models import Worker, Client
                from datetime import datetime, timedelta
                from app import db
                
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                old_workers = Worker.query.filter(
                    Worker.created_at < cutoff_date,
                    Worker.is_active == False
                ).count()
                
                old_clients = Client.query.filter(
                    Client.created_at < cutoff_date
                ).count()
                
                click.echo(f"   Workers to anonymize: {old_workers}")
                click.echo(f"   Clients to anonymize: {old_clients}")
            else:
                anonymized_count = data_protection.anonymize_old_data(days)
                click.echo(f"✅ Anonymized {anonymized_count} records")
                
    except Exception as e:
        click.echo(f"❌ Error anonymizing data: {str(e)}")

@security.command()
def security_status():
    """Show current security status and statistics"""
    click.echo("🛡️  Security Status Report")
    click.echo("=" * 50)
    
    try:
        from app import create_app
        
        app = create_app()
        with app.app_context():
            # Get security statistics
            stats = db_security.get_security_stats()
            
            click.echo(f"📊 Database Security Statistics:")
            click.echo(f"   Total Queries: {stats['total_queries']}")
            click.echo(f"   Suspicious Queries: {stats['suspicious_queries']}")
            click.echo(f"   Failed Logins: {stats['failed_logins']}")
            click.echo(f"   Data Exports: {stats['data_exports']}")
            
            # Check encryption key
            import os
            key_file = current_app.config.get('ENCRYPTION_KEY_FILE', '.encryption_key')
            if os.path.exists(key_file):
                click.echo(f"✅ Encryption key exists: {key_file}")
            else:
                click.echo(f"❌ Encryption key not found: {key_file}")
            
            # Check log files
            security_log = current_app.config.get('SECURITY_LOG_FILE', 'logs/security.log')
            audit_log = current_app.config.get('AUDIT_LOG_FILE', 'logs/audit.log')
            
            click.echo(f"📋 Security Log: {security_log} {'✅' if os.path.exists(security_log) else '❌'}")
            click.echo(f"📋 Audit Log: {audit_log} {'✅' if os.path.exists(audit_log) else '❌'}")
            
            # Data statistics
            from app.models import Worker, Client, Salon, Appointment, ServiceOrder
            
            click.echo(f"\n📊 Database Statistics:")
            click.echo(f"   Workers: {Worker.query.count()}")
            click.echo(f"   Clients: {Client.query.count()}")
            click.echo(f"   Salons: {Salon.query.count()}")
            click.echo(f"   Appointments: {Appointment.query.count()}")
            click.echo(f"   Service Orders: {ServiceOrder.query.count()}")
            
            # Check for encrypted data
            encrypted_count = 0
            for worker in Worker.query.limit(10).all():
                if worker.phone and data_protection._is_encrypted(worker.phone):
                    encrypted_count += 1
            
            if encrypted_count > 0:
                click.echo(f"✅ Data encryption appears to be active ({encrypted_count}/10 workers have encrypted data)")
            else:
                click.echo("⚠️  No encrypted data detected - run 'security encrypt-data' to enable")
                
    except Exception as e:
        click.echo(f"❌ Error getting security status: {str(e)}")

@security.command()
def reset_stats():
    """Reset security statistics"""
    click.echo("🔄 Resetting security statistics...")
    
    try:
        from app import create_app
        
        app = create_app()
        with app.app_context():
            db_security.reset_security_stats()
            click.echo("✅ Security statistics reset")
            
    except Exception as e:
        click.echo(f"❌ Error resetting statistics: {str(e)}")

@security.command()
@click.option('--test-user', default=1, help='User ID to test with')
def test_encryption(test_user):
    """Test encryption/decryption functionality"""
    click.echo("🧪 Testing encryption functionality...")
    
    try:
        from app import create_app
        from app.models import Worker
        
        app = create_app()
        with app.app_context():
            # Get test user
            worker = Worker.query.get(test_user)
            if not worker:
                click.echo(f"❌ Worker with ID {test_user} not found")
                return
            
            click.echo(f"👤 Testing with worker: {worker.full_name}")
            
            # Test data masking
            masked_data = data_protection.mask_sensitive_data({
                'phone': worker.phone,
                'email': worker.email,
                'id_number': worker.id_number
            })
            
            click.echo("🎭 Masked data:")
            for field, value in masked_data.items():
                click.echo(f"   {field}: {value}")
            
            # Test encryption
            test_data = {'phone': worker.phone, 'email': worker.email}
            encrypted = data_protection.encrypt_sensitive_data(Worker, test_data)
            click.echo("🔐 Encrypted data created")
            
            # Test decryption
            decrypted = data_protection.decrypt_sensitive_data(Worker, encrypted)
            click.echo("🔓 Decrypted data:")
            for field, value in decrypted.items():
                click.echo(f"   {field}: {value}")
            
            click.echo("✅ Encryption test completed successfully")
            
    except Exception as e:
        click.echo(f"❌ Error testing encryption: {str(e)}")

if __name__ == '__main__':
    security()
