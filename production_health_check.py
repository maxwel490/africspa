#!/usr/bin/env python3
"""
Production Health Check Script
Tests all critical endpoints and functionality for production deployment
"""

import os
import sys
from app import create_app, db
from app.models import Worker, Salon, Branch, PricingConfig

def run_production_health_check():
    """
    Comprehensive health check for production deployment
    """
    
    app = create_app()
    
    with app.app_context():
        print("=== Production Health Check ===")
        
        # 1. Application Configuration
        print("\n1. Application Configuration")
        config_checks = {
            'DEBUG mode disabled': not app.config.get('DEBUG', True),
            'Secret key set': bool(app.config.get('SECRET_KEY') and app.config['SECRET_KEY'] != 'africspa-production-fallback-key'),
            'Database URI configured': bool(app.config.get('SQLALCHEMY_DATABASE_URI')),
            'HTTPS enforcement': app.config.get('FORCE_HTTPS', False),
            'Cookie security': app.config.get('SESSION_COOKIE_SECURE', False),
        }
        
        for check, passed in config_checks.items():
            status = "✓" if passed else "✗"
            print(f"  {status} {check}")
        
        # 2. Database Connectivity
        print("\n2. Database Connectivity")
        try:
            db.session.execute(db.text("SELECT 1"))
            print("  ✓ Database connection successful")
            
            # Check critical tables
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            critical_tables = ['workers', 'salons', 'branches', 'pricing_config']
            
            for table in critical_tables:
                if table in tables:
                    print(f"  ✓ Table '{table}' exists")
                else:
                    print(f"  ✗ Table '{table}' missing")
                    
        except Exception as e:
            print(f"  ✗ Database connection failed: {e}")
        
        # 3. Critical Data
        print("\n3. Critical Data")
        try:
            worker_count = db.session.query(Worker).count()
            salon_count = db.session.query(Salon).count()
            branch_count = db.session.query(Branch).count()
            pricing_count = db.session.query(PricingConfig).count()
            
            print(f"  ✓ Workers: {worker_count}")
            print(f"  ✓ Salons: {salon_count}")
            print(f"  ✓ Branches: {branch_count}")
            print(f"  ✓ Pricing configs: {pricing_count}")
            
        except Exception as e:
            print(f"  ✗ Data check failed: {e}")
        
        # 4. Security Configuration
        print("\n4. Security Configuration")
        try:
            from production_security_config import validate_security_config
            security_valid = validate_security_config(app)
            status = "✓" if security_valid else "✗"
            print(f"  {status} Security configuration validated")
        except Exception as e:
            print(f"  ✗ Security check failed: {e}")
        
        # 5. Template Rendering
        print("\n5. Template Rendering")
        critical_templates = [
            'base.html',
            'superadmin/superadmin_base.html',
            'superadmin/pricing_management.html',
            'admin/dashboard.html',
            'auth/login.html'
        ]
        
        for template in critical_templates:
            try:
                with app.test_request_context():
                    app.jinja_env.get_template(template)
                print(f"  ✓ Template '{template}' renders")
            except Exception as e:
                print(f"  ✗ Template '{template}' error: {e}")
        
        # 6. Route Registration
        print("\n6. Route Registration")
        critical_routes = [
            ('/', 'main.index'),
            ('/auth/login', 'auth.login'),
            ('/admin/', 'admin.dashboard'),
            ('/superadmin/', 'superadmin.dashboard'),
            ('/superadmin/pricing/', 'superadmin_pricing.pricing_management'),
        ]
        
        for url, expected_endpoint in critical_routes:
            try:
                with app.test_client() as client:
                    response = client.get(url, follow_redirects=False)
                    # Check if route exists (not checking for auth success)
                    if response.status_code in [200, 302, 403]:
                        print(f"  ✓ Route '{url}' accessible")
                    else:
                        print(f"  ! Route '{url}' returned {response.status_code}")
            except Exception as e:
                print(f"  ✗ Route '{url}' error: {e}")
        
        # 7. Static Files
        print("\n7. Static Files")
        static_files = [
            'css/bootstrap.min.css',
            'js/bootstrap.bundle.min.js',
            'favicon.ico'
        ]
        
        for static_file in static_files:
            try:
                with app.test_client() as client:
                    response = client.get(f'/static/{static_file}')
                    if response.status_code == 200:
                        print(f"  ✓ Static file '{static_file}' accessible")
                    else:
                        print(f"  ✗ Static file '{static_file}' missing")
            except Exception as e:
                print(f"  ✗ Static file '{static_file}' error: {e}")
        
        # 8. Logging Configuration
        print("\n8. Logging Configuration")
        log_files = ['logs/app.log', 'logs/error.log', 'logs/security.log']
        
        for log_file in log_files:
            if os.path.exists(log_file):
                print(f"  ✓ Log file '{log_file}' exists")
            else:
                print(f"  ! Log file '{log_file}' will be created on first use")
        
        print("\n=== Health Check Complete ===")
        print("\nNext Steps:")
        print("1. Set environment variables from .env.production")
        print("2. Configure production database")
        print("3. Set up SSL certificates")
        print("4. Deploy with WSGI server")
        print("5. Monitor logs in logs/ directory")

if __name__ == "__main__":
    run_production_health_check()
