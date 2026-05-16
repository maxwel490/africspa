import os

class Config:
    # --- 1. Environment & Security ---
    DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'
    FORCE_HTTPS = os.environ.get('FORCE_HTTPS', '0') == '1'

    # Persistent secret key for production security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'africspa-production-fallback-key'

    # Production Cookie Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = FORCE_HTTPS
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = FORCE_HTTPS
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    # Payload & Request Limits
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
    MAX_FORM_MEMORY_SIZE = int(os.environ.get('MAX_FORM_MEMORY_SIZE', 2 * 1024 * 1024))
    MAX_FORM_PARTS = int(os.environ.get('MAX_FORM_PARTS', 1000))

    # --- 2. Database Configuration (Local Development vs Production) ---
    
    # Check if we're in local development mode
    is_local_dev = (
        os.environ.get('FLASK_DEBUG', '0') == '1' or 
        os.environ.get('ENV', 'production') == 'development'
    )
    
    if is_local_dev:
        # Local Development (XAMPP MySQL)
        DB_USER = os.environ.get('DB_USER', 'root')
        DB_PASS = os.environ.get('DB_PASS', '')
        DB_NAME = os.environ.get('DB_NAME', 'africspa_db')
        DB_HOST = os.environ.get('DB_HOST', 'localhost')
        DB_SOCKET = os.environ.get('DB_SOCKET', '/opt/lampp/var/mysql/mysql.sock')
        
        # Local development connection with socket
        MYSQL_URI = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}?unix_socket={DB_SOCKET}"
    else:
        # Production (cPanel MySQL)
        DB_USER = os.environ.get('DB_USER', 'africspa_MaxwelKithole')
        DB_PASS = os.environ.get('DB_PASS', 'MaxwelKithole$$24')
        DB_NAME = os.environ.get('DB_NAME', 'africspa_africadb')
        DB_HOST = os.environ.get('DB_HOST', 'localhost')
        
        # Production connection
        MYSQL_URI = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

    # Priority: DATABASE_URL (if set) or the constructed MYSQL_URI
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or MYSQL_URI

    # --- 3. SQLAlchemy Performance & Stability ---
    # Optimized for continental scaling
    pool_size = int(os.environ.get('DB_POOL_SIZE', '20'))
    max_overflow = int(os.environ.get('DB_MAX_OVERFLOW', '40'))
    
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,    # Verifies connection health before use
        "pool_recycle": 280,      # Stays under MySQL 300s timeout
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_timeout": 30,
        "pool_recycle": 3600,     # Hourly connection recycle
    }
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- 4. OAuth & Security Settings ---
    BASE_URL = os.environ.get('BASE_URL', 'https://beautyspace.co.ke')
    
    # Security Policy Configuration
    MAX_LOGIN_ATTEMPTS = int(os.environ.get('MAX_LOGIN_ATTEMPTS', '5'))
    ACCOUNT_LOCKOUT_MINUTES = int(os.environ.get('ACCOUNT_LOCKOUT_MINUTES', '30'))
    PASSWORD_EXPIRE_DAYS = int(os.environ.get('PASSWORD_EXPIRE_DAYS', '90'))
    PASSWORD_HISTORY_COUNT = int(os.environ.get('PASSWORD_HISTORY_COUNT', '5'))