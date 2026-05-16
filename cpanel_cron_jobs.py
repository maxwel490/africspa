#!/usr/bin/env python3
"""
cPanel Cron Job Scripts
Maintenance scripts for cPanel deployment
"""

import os
import sys
import subprocess
import datetime
import shutil

def backup_database():
    """
    Database backup script for cPanel cron job
    """
    try:
        # Import app configuration
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from config import Config
        
        # Create backup filename with timestamp
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)
        
        # For SQLite
        if Config.USING_SQLITE:
            db_file = Config.SQLITE_PATH
            backup_file = os.path.join(backup_dir, f'africspa_backup_{timestamp}.db')
            shutil.copy2(db_file, backup_file)
            print(f"SQLite backup created: {backup_file}")
        
        # For MySQL (requires mysqldump)
        else:
            backup_file = os.path.join(backup_dir, f'africspa_backup_{timestamp}.sql')
            cmd = [
                'mysqldump',
                f'--host={Config.DB_HOST}',
                f'--user={Config.DB_USER}',
                f'--password={Config.DB_PASS}',
                Config.DB_NAME,
                '--result-file=' + backup_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"MySQL backup created: {backup_file}")
            else:
                print(f"MySQL backup failed: {result.stderr}")
                return False
        
        # Clean old backups (keep last 7 days)
        cleanup_old_backups(backup_dir, days=7)
        return True
        
    except Exception as e:
        print(f"Backup failed: {e}")
        return False

def cleanup_old_backups(backup_dir, days=7):
    """
    Clean up old backup files
    """
    try:
        cutoff_time = datetime.datetime.now() - datetime.timedelta(days=days)
        
        for filename in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, filename)
            if os.path.isfile(file_path):
                file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_time < cutoff_time:
                    os.remove(file_path)
                    print(f"Removed old backup: {filename}")
        
    except Exception as e:
        print(f"Cleanup failed: {e}")

def rotate_logs():
    """
    Log rotation script for cPanel cron job
    """
    try:
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            return
        
        # Rotate logs older than 30 days
        cutoff_time = datetime.datetime.now() - datetime.timedelta(days=30)
        
        for filename in os.listdir(log_dir):
            if filename.endswith('.log'):
                file_path = os.path.join(log_dir, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_time < cutoff_time:
                        # Compress old log
                        compressed_file = file_path + '.gz'
                        with open(file_path, 'rb') as f_in:
                            import gzip
                            with gzip.open(compressed_file, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        os.remove(file_path)
                        print(f"Compressed log: {filename}")
    
    except Exception as e:
        print(f"Log rotation failed: {e}")

def health_check():
    """
    Application health check for cPanel cron job
    """
    try:
        # Import app
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app import create_app, db
        
        app = create_app()
        with app.app_context():
            # Test database connection
            db.session.execute(db.text("SELECT 1"))
            
            # Check critical tables
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            critical_tables = ['workers', 'salons', 'branches', 'pricing_config']
            missing_tables = [t for t in critical_tables if t not in tables]
            
            if missing_tables:
                print(f"Missing tables: {missing_tables}")
                return False
            
            print("Health check passed")
            return True
    
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

def update_ssl_certificates():
    """
    SSL certificate renewal check (for Let's Encrypt)
    """
    try:
        # This would typically be handled by cPanel's AutoSSL
        # But we can add custom checks here
        print("SSL certificate check - handled by cPanel AutoSSL")
        return True
    
    except Exception as e:
        print(f"SSL check failed: {e}")
        return False

def main():
    """
    Main script runner - called by cron jobs
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='cPanel maintenance scripts')
    parser.add_argument('--backup', action='store_true', help='Run database backup')
    parser.add_argument('--rotate-logs', action='store_true', help='Rotate log files')
    parser.add_argument('--health-check', action='store_true', help='Run health check')
    parser.add_argument('--ssl-check', action='store_true', help='Check SSL certificates')
    
    args = parser.parse_args()
    
    if args.backup:
        backup_database()
    
    if args.rotate_logs:
        rotate_logs()
    
    if args.health_check:
        health_check()
    
    if args.ssl_check:
        update_ssl_certificates()
    
    # If no arguments, show help
    if not any(vars(args).values()):
        parser.print_help()

if __name__ == "__main__":
    main()
