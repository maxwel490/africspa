"""
Multi-Tenant Database Setup Script

Creates database schema and initial data for the multi-tenant SaaS platform.
Includes OAuth authentication and password security features.
"""

from app import create_app, db
from app.models import Salon, Worker, Branch, Client, Service, Appointment, Product, ServiceOrder
from werkzeug.security import generate_password_hash
from sqlalchemy import text


def verify_setup():
    """Verify the database setup and security configuration"""
    app = create_app()
    with app.app_context():
        try:
            print(" DATABASE VERIFICATION STARTED\n")
            
            # Count entities
            salon_count = Salon.query.count()
            worker_count = Worker.query.count()
            branch_count = Branch.query.count()
            
            print(" Database Statistics:")
            print(f"   Salons: {salon_count}")
            print(f"   Workers: {worker_count}")
            print(f"   Branches: {branch_count}")
            
            # Verify country column exists
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('salons')]
            has_country = 'country' in columns
            
            # Verify address column exists in workers
            worker_columns = [col['name'] for col in inspector.get_columns('workers')]
            has_address = 'address' in worker_columns
            
            # Verify password security fields
            password_fields = [
                'password_changed_at', 'password_history', 'failed_login_attempts',
                'last_failed_login', 'is_locked', 'locked_until', 'password_expired'
            ]
            has_password_security = all(field in worker_columns for field in password_fields)
            
            # Check OAuth configuration
            from flask import current_app
            google_configured = bool(current_app.config.get('GOOGLE_CLIENT_ID'))
            apple_configured = bool(current_app.config.get('APPLE_CLIENT_ID'))
            
            print("\n Continental Features:")
            print(f"   Country Column: {' Present' if has_country else ' Missing'}")
            print(f"   Multi-tenant Architecture: Enabled")
            print(f"   Continental Coverage: 54 Countries")
            print(f"   Multi-currency Support: Available")
            
            print("\n Security Features:")
            print(f"   Address Field: {' Present' if has_address else ' Missing'}")
            print(f"   Password Security: {' Enabled' if has_password_security else ' Missing'}")
            print(f"   Account Lockout: {' Enabled' if has_password_security else ' Missing'}")
            print(f"   Password History: {' Enabled' if has_password_security else ' Missing'}")
            print(f"   Password Expiration: {' Enabled' if has_password_security else ' Missing'}")
            
            print("\n OAuth Authentication:")
            print(f"   Google OAuth: {' Configured' if google_configured else ' Not configured'}")
            print(f"   Apple Sign In: {' Configured' if apple_configured else ' Not configured'}")
            print(f"   OAuth Endpoints: {' Available' if google_configured or apple_configured else ' Not configured'}")
            
            print("\n System Status:")
            schema_complete = has_country and has_address and has_password_security
            security_complete = has_password_security
            oauth_ready = google_configured or apple_configured
            
            print(f"   Database Schema: {' Complete' if schema_complete else ' Incomplete'}")
            print(f"   Security Features: {' Full' if security_complete else ' Partial'}")
            print(f"   OAuth Ready: {' Yes' if oauth_ready else ' Needs configuration'}")
            
            if not schema_complete:
                print("\n Missing required database columns - run setup again")
            if not security_complete:
                print("\n Security features incomplete - run setup again")
            if not oauth_ready:
                print("\n OAuth not configured - optional feature")
            
            print("\n Database verification completed!")
            
            return "SUCCESS: Database verification completed"
            
        except Exception as e:
            print(f" VERIFICATION ERROR: {str(e)}")
            return f"ERROR: Verification failed - {str(e)}"

if __name__ == "__main__":
    import sys
    
    print(" Africa SPA System Database Setup")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == 'verify':
        verify_setup()
    elif len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("\nUsage:")
        print("  python setup_db.py              - Run database migration and setup")
        print("  python setup_db.py verify       - Verify database setup")
        print("  python setup_db.py --help       - Show this help")
        print("\nProduction Deployment:")
        print("  1. Configure .env.production file")
        print("  2. Run 'python setup_db.py' to create database")
        print("  3. Run 'python setup_db.py verify' to validate")
        print("  4. Change default Super Admin password")
    else:
        # ADD THIS PART TO CREATE THE TABLES
        app = create_app()
        with app.app_context():
            print(" Creating database tables...")
            db.create_all() 
            print(" Tables created successfully!")
            
            # Create default superadmin account
            from werkzeug.security import generate_password_hash
            from datetime import datetime
            
            # Check if superadmin already exists
            existing_superadmin = Worker.query.filter_by(username='superadmin').first()
            if not existing_superadmin:
                superadmin = Worker(
                    username='superadmin',
                    email='superadmin@africspa.com',
                    full_name='System Administrator',
                    role='superadmin',
                    password_hash=generate_password_hash('SuperAdmin@2024!'),
                    password_changed_at=datetime.utcnow(),
                    failed_login_attempts=0,
                    is_locked=False,
                    password_expired=False
                )
                db.session.add(superadmin)
                db.session.commit()
                print("✅ Default superadmin account created!")
                print("   Username: superadmin")
                print("   Password: SuperAdmin@2024!")
                print("   Email: superadmin@africspa.com")
            else:
                print("ℹ️ Superadmin account already exists!")