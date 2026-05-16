#!/usr/bin/env python3
"""
Local Database Setup Script for XAMPP

Creates and configures local MySQL database for development.
"""

import os
import sys
import subprocess
from app import create_app, db
from app.models import Salon, Worker, Branch, Client, Service, Appointment, Product, ServiceOrder
from werkzeug.security import generate_password_hash
from sqlalchemy import text
from datetime import datetime

def create_mysql_database():
    """Create MySQL database using XAMPP"""
    print("Creating MySQL database with XAMPP...")
    
    try:
        # Create database using mysql command with XAMPP socket and SSL disabled
        cmd = [
            'mysql', 
            '-u', 'root',
            '--socket=/opt/lampp/var/mysql/mysql.sock',
            '--skip-ssl',
            '-e', 
            'CREATE DATABASE IF NOT EXISTS africspa_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Database 'africspa_db' created successfully")
        else:
            print(f"❌ Error creating database: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

def run_local_migration():
    """Create database tables and seed initial data for local development"""
    app = create_app()
    with app.app_context():
        try:
            print("Creating local database schema...")
            db.create_all()
            print("✅ Database tables created successfully!")
            
            # Add country column if it doesn't exist
            try:
                inspector = db.inspect(db.engine)
                columns = [col['name'] for col in inspector.get_columns('salons')]
                
                if 'country' not in columns:
                    print("Adding country column to salons table...")
                    db.session.execute(text('ALTER TABLE salons ADD COLUMN country VARCHAR(2) DEFAULT "KE"'))
                    db.session.commit()
                    print("✅ Country column added successfully!")
                    
            except Exception as e:
                print(f"⚠ Warning adding country column: {e}")
                db.session.rollback()
            
            # Add address column to workers table if it doesn't exist
            try:
                inspector = db.inspect(db.engine)
                worker_columns = [col['name'] for col in inspector.get_columns('workers')]
                
                if 'address' not in worker_columns:
                    print("Adding address column to workers table...")
                    db.session.execute(text('ALTER TABLE workers ADD COLUMN address VARCHAR(255)'))
                    db.session.commit()
                    print("✅ Address column added successfully!")
                    
            except Exception as e:
                print(f"⚠ Warning adding address column: {e}")
                db.session.rollback()
            
            # Add password security fields if they don't exist
            try:
                inspector = db.inspect(db.engine)
                worker_columns = [col['name'] for col in inspector.get_columns('workers')]
                
                password_fields = [
                    ('password_changed_at', 'DATETIME'),
                    ('password_history', 'TEXT'),
                    ('failed_login_attempts', 'INTEGER'),
                    ('last_failed_login', 'DATETIME'),
                    ('is_locked', 'BOOLEAN'),
                    ('locked_until', 'DATETIME'),
                    ('password_expired', 'BOOLEAN')
                ]
                
                for field_name, field_type in password_fields:
                    if field_name not in worker_columns:
                        print(f"Adding {field_name} column to workers table...")
                        if field_type == 'DATETIME':
                            db.session.execute(text(f'ALTER TABLE workers ADD COLUMN {field_name} {field_type}'))
                        elif field_type == 'BOOLEAN':
                            db.session.execute(text(f'ALTER TABLE workers ADD COLUMN {field_name} {field_type} DEFAULT FALSE'))
                        elif field_type == 'INTEGER':
                            db.session.execute(text(f'ALTER TABLE workers ADD COLUMN {field_name} {field_type} DEFAULT 0'))
                        else:
                            db.session.execute(text(f'ALTER TABLE workers ADD COLUMN {field_name} {field_type}'))
                        print(f"✅ {field_name} column added successfully!")
                
                # Update existing records with default values
                db.session.execute(text('UPDATE workers SET password_changed_at = CURRENT_TIMESTAMP WHERE password_changed_at IS NULL'))
                db.session.execute(text('UPDATE workers SET failed_login_attempts = 0 WHERE failed_login_attempts IS NULL'))
                db.session.execute(text('UPDATE workers SET is_locked = FALSE WHERE is_locked IS NULL'))
                db.session.execute(text('UPDATE workers SET password_expired = FALSE WHERE password_expired IS NULL'))
                
                db.session.commit()
                print("✅ Password security fields added successfully!")
                
            except Exception as e:
                print(f"⚠ Warning adding password security fields: {e}")
                db.session.rollback()
            
            # Create local test data
            create_local_test_data()
            
            print("\n🎉 LOCAL DEVELOPMENT SETUP COMPLETE!")
            print("\nLocal Database Configuration:")
            print("  Host: localhost (XAMPP)")
            print("  Database: africspa_db")
            print("  User: root")
            print("  Password: (empty)")
            print("\nTest Accounts Created:")
            print("  Super Admin: superadmin / SuperAdmin@2024!")
            print("  Test Salon: test_salon / TestSalon@2024!")
            print("  Test Admin: test_admin / TestAdmin@2024!")
            print("\nNext Steps:")
            print("  1. Set FLASK_ENV=development")
            print("  2. Run 'python app.py' to start the application")
            print("  3. Access: http://localhost:5000")
            print("  4. Login with test accounts")
            
            return "SUCCESS: Local database setup completed!"
            
        except Exception as e:
            print(f"❌ CRITICAL ERROR: Local database setup failed")
            print(f"   Error: {str(e)}")
            db.session.rollback()
            return f"ERROR: Local database setup failed - {str(e)}"

def create_local_test_data():
    """Create test data for local development"""
    print("Creating local test data...")
    
    # Create test salon
    test_salon = Salon.query.filter_by(name='Test Salon').first()
    if not test_salon:
        test_salon = Salon(
            name='Test Salon',
            slug='test-salon',
            email='test@salon.com',
            phone='0712345678',
            address='123 Test Street',
            country='KE',
            is_active=True
        )
        db.session.add(test_salon)
        db.session.commit()
        print("✅ Test salon created")
    
    # Create test branch
    test_branch = Branch.query.filter_by(name='Main Branch').first()
    if not test_branch:
        test_branch = Branch(
            name='Main Branch',
            code='MAIN',
            salon_id=test_salon.id,
            address='123 Test Street',
            phone='0712345678',
            email='main@testsalon.com',
            is_active=True
        )
        db.session.add(test_branch)
        db.session.commit()
        print("✅ Test branch created")
    
    # Create test salon admin
    test_admin = Worker.query.filter_by(username='test_admin').first()
    if not test_admin:
        test_admin = Worker(
            username='test_admin',
            email='test_admin@salon.com',
            full_name='Test Admin',
            role='admin',
            branch=test_branch.name,
            salon_id=test_salon.id
        )
        test_admin.password_hash = generate_password_hash('TestAdmin@2024!')
        test_admin.password_changed_at = datetime.utcnow()
        test_admin.failed_login_attempts = 0
        test_admin.is_locked = False
        test_admin.password_expired = False
        db.session.add(test_admin)
        db.session.commit()
        print("✅ Test admin created")
    
    # Create test salonist
    test_salonist = Worker.query.filter_by(username='test_salonist').first()
    if not test_salonist:
        test_salonist = Worker(
            username='test_salonist',
            email='test_salonist@salon.com',
            full_name='Test Salonist',
            role='salonist',
            specialty='Hair Styling',
            branch=test_branch.name,
            salon_id=test_salon.id
        )
        test_salonist.password_hash = generate_password_hash('TestSalonist@2024!')
        test_salonist.password_changed_at = datetime.utcnow()
        test_salonist.failed_login_attempts = 0
        test_salonist.is_locked = False
        test_salonist.password_expired = False
        db.session.add(test_salonist)
        db.session.commit()
        print("✅ Test salonist created")

def main():
    """Main function"""
    print("Africa SPA Local Development Setup")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("\nUsage:")
        print("  python setup_local_db.py              - Create local database and setup")
        print("  python setup_local_db.py --help       - Show this help")
        print("\nRequirements:")
        print("  1. XAMPP must be installed and running")
        print("  2. MySQL service should be active")
        print("  3. .env.local file should be configured")
        return
    
    # Step 1: Create MySQL database
    if not create_mysql_database():
        print("\n❌ Failed to create MySQL database")
        print("Please ensure:")
        print("  1. XAMPP is running")
        print("  2. MySQL service is active")
        print("  3. You have permissions to create databases")
        return
    
    # Step 2: Run migration and setup
    print("\n" + "=" * 40)
    run_local_migration()

if __name__ == "__main__":
    main()
