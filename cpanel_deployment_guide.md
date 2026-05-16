# cPanel Deployment Guide

## Overview
This guide covers deploying the Africa SPA System on cPanel with Phusion Passenger.

## Prerequisites
- cPanel hosting account with Python support
- MySQL database access
- SSH access to cPanel
- Domain configured

## Step 1: Upload Files

### Upload via File Manager or FTP
1. Upload all project files to your cPanel home directory
2. Ensure the directory structure is maintained:
   ```
   /home/username/
   ├── africspa.com/
   ├── app/
   ├── config.py
   ├── app.py
   ├── passenger_wsgi.py
   ├── .htaccess
   └── requirements.txt
   ```

### Set Permissions
```bash
# SSH commands
chmod 755 /home/username/africspa.com
chmod 644 /home/username/africspa.com/*.py
chmod 755 /home/username/africspa.com/app
```

## Step 2: Setup Python Environment

### via cPanel Setup Python App
1. Go to cPanel > Setup Python App
2. Click "Create Application"
3. Configure:
   - **Python Version**: 3.9 or higher
   - **Application Root**: africspa.com
   - **Application URL**: yourdomain.com
   - **Application Startup File**: passenger_wsgi.py
   - **Application Entry Point**: application

### Install Dependencies
```bash
# In cPanel terminal or SSH
cd /home/username/africspa.com
source /home/username/virtualenv/africspa.com/bin/activate
pip install -r requirements.txt
```

## Step 3: Database Configuration

### Create MySQL Database
1. In cPanel > MySQL Databases
2. Create database: `username_africspa`
3. Create user: `username_africspa_user`
4. Grant all privileges

### Configure Database
1. Copy `.env.production` to `.env`
2. Update database credentials:
   ```bash
   DB_USER=username_africspa_user
   DB_PASS=your_database_password
   DB_NAME=username_africspa
   DB_HOST=localhost
   ```

### Run Migrations
```bash
cd /home/username/africspa.com
source /home/username/virtualenv/africspa.com/bin/activate
flask db upgrade
```

## Step 4: Environment Variables

### Set Production Environment
1. In cPanel > Setup Python App > Environment Variables
2. Add required variables:
   ```
   ENV=production
   FLASK_DEBUG=0
   SECRET_KEY=your-strong-secret-key
   ENABLE_TALISMAN=1
   FORCE_HTTPS=1
   BASE_URL=https://yourdomain.com
   ```

## Step 5: Configure passenger_wsgi.py

The `passenger_wsgi.py` file is already configured for cPanel. Ensure it contains:

```python
import importlib.util
import os
import sys

# Define the project root and ensure it's in the system path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Path to your entry point (app.py)
app_path = os.path.join(project_root, 'app.py')

# Modern dynamic import using importlib
spec = importlib.util.spec_from_file_location('wsgi', app_path)
if spec and spec.loader:
    wsgi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wsgi)
    # Phusion Passenger looks for the 'application' callable
    application = wsgi.application
else:
    raise ImportError(f"Could not load setup from {app_path}")
```

## Step 6: .htaccess Configuration

Create `.htaccess` in the project root:

```apache
# Enable Passenger
PassengerAppRoot /home/username/africspa.com
PassengerBaseURI /
PassengerPython /home/username/virtualenv/africspa.com/bin/python

# Security headers
<IfModule mod_headers.c>
    Header always set X-Frame-Options DENY
    Header always set X-Content-Type-Options nosniff
    Header always set X-XSS-Protection "1; mode=block"
    Header always set Referrer-Policy "strict-origin-when-cross-origin"
    Header always set Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://www.google.com https://accounts.google.com;"
</IfModule>

# HTTPS redirect
RewriteEngine On
RewriteCond %{HTTPS} off
RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]

# Static file caching
<IfModule mod_expires.c>
    ExpiresActive On
    ExpiresByType text/css "access plus 1 year"
    ExpiresByType application/javascript "access plus 1 year"
    ExpiresByType image/png "access plus 1 year"
    ExpiresByType image/jpg "access plus 1 year"
    ExpiresByType image/jpeg "access plus 1 year"
    ExpiresByType image/gif "access plus 1 year"
    ExpiresByType image/ico "access plus 1 year"
    ExpiresByType image/svg+xml "access plus 1 year"
    ExpiresByType font/woff "access plus 1 year"
    ExpiresByType font/woff2 "access plus 1 year"
</IfModule>

# Compression
<IfModule mod_deflate.c>
    AddOutputFilterByType DEFLATE text/css
    AddOutputFilterByType DEFLATE application/javascript
    AddOutputFilterByType DEFLATE text/html
    AddOutputFilterByType DEFLATE text/plain
    AddOutputFilterByType DEFLATE image/svg+xml
</IfModule>
```

## Step 7: SSL Certificate

### Install SSL Certificate
1. In cPanel > SSL/TLS
2. Use "Let's Encrypt" to install free SSL
3. Ensure HTTPS is enforced

## Step 8: Cron Jobs

### Setup Maintenance Cron Jobs
1. In cPanel > Cron Jobs
2. Add daily backup job:
   ```bash
   0 2 * * * /home/username/virtualenv/africspa.com/bin/python /home/username/africspa.com/backup_database.py
   ```

3. Add log rotation:
   ```bash
   0 3 * * * /usr/bin/find /home/username/africspa.com/logs -name "*.log" -mtime +30 -delete
   ```

## Step 9: Testing

### Test Application
1. Restart the Python app in cPanel
2. Visit your domain
3. Check all critical pages:
   - Homepage
   - Login page
   - Admin dashboard
   - Superadmin pricing management

### Test Database
```bash
cd /home/username/africspa.com
source /home/username/virtualenv/africspa.com/bin/activate
python -c "from app import create_app, db; app = create_app(); with app.app_context(): print('Database connected:', db.session.execute('SELECT 1').scalar())"
```

## Step 10: Monitoring

### Log Files Location
- Application logs: `/home/username/africspa.com/logs/app.log`
- Error logs: `/home/username/africspa.com/logs/error.log`
- Security logs: `/home/username/africspa.com/logs/security.log`
- Passenger logs: `/home/username/logs/passenger.log`

### Monitor in cPanel
1. cPanel > Metrics > Errors
2. Check Passenger application status
3. Monitor disk space usage

## Troubleshooting

### Common Issues

#### 500 Internal Server Error
1. Check passenger logs: `tail -f /home/username/logs/passenger.log`
2. Verify Python dependencies
3. Check file permissions

#### Database Connection Error
1. Verify database credentials in `.env`
2. Check database user permissions
3. Test database connection manually

#### Static Files Not Loading
1. Check `.htaccess` configuration
2. Verify file permissions
3. Clear browser cache

#### Application Not Starting
1. Restart Python app in cPanel
2. Check syntax errors in Python files
3. Verify environment variables

### Performance Optimization

#### Database Optimization
1. Enable MySQL query cache
2. Add indexes to frequently queried columns
3. Monitor slow queries

#### Application Optimization
1. Enable static file caching
2. Use CDN for external resources
3. Monitor memory usage

## Security Best Practices

### File Permissions
```bash
# Secure permissions
find /home/username/africspa.com -type f -name "*.py" -exec chmod 644 {} \;
find /home/username/africspa.com -type d -exec chmod 755 {} \;
chmod 600 /home/username/africspa.com/.env
```

### Regular Maintenance
1. Update dependencies monthly
2. Backup database daily
3. Monitor security logs
4. Update SSL certificates

### Security Headers
- Content Security Policy (CSP) enabled
- HTTPS enforced
- Security headers configured
- Database credentials secured

## Support

For cPanel-specific issues:
1. Check cPanel error logs
2. Contact hosting provider support
3. Review cPanel documentation

For application issues:
1. Check application logs
2. Verify database connectivity
3. Test configuration settings
