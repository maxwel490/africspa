# Production Deployment Guide

## Environment Variables Setup

### 1. Copy the production environment template
```bash
cp .env.production .env
```

### 2. Set Required Environment Variables

#### Critical Security Variables
- `SECRET_KEY`: Generate a strong, unique secret key
- `ENABLE_TALISMAN=1`: Enable security headers
- `FORCE_HTTPS=1`: Force HTTPS in production
- `FLASK_DEBUG=0`: Disable debug mode

#### Database Configuration
- `DATABASE_URL`: Full MySQL connection string
- `DB_USER`: Database username
- `DB_PASS`: Database password
- `DB_NAME`: Database name
- `DB_HOST`: Database host

#### Application Configuration
- `BASE_URL`: Your production domain (e.g., https://your-domain.com)
- `ENV=production`: Set environment to production

#### OAuth Configuration (Optional)
- `GOOGLE_CLIENT_ID`: Google OAuth client ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth client secret
- `APPLE_CLIENT_ID`: Apple Sign In client ID
- `APPLE_CLIENT_SECRET`: Apple Sign In client secret

## Security Checklist

### ✅ Completed Security Measures
- [x] Enhanced CSP headers configured
- [x] Security validation implemented
- [x] Debug code removed
- [x] Production logging configured
- [x] Static assets optimized
- [x] Database connection pooling configured

### 🔒 Security Headers Enabled
- Content Security Policy (CSP)
- HTTP Strict Transport Security (HSTS)
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- X-XSS-Protection
- Referrer Policy

### 📊 Logging Configuration
- Application logs: `logs/app.log`
- Error logs: `logs/error.log`
- Security logs: `logs/security.log`
- Audit logs: `logs/audit.log`

## Database Setup

### MySQL Production Database
1. Create MySQL database
2. Set proper user permissions
3. Configure connection pooling
4. Run migrations: `flask db upgrade`

### Database Security
- Use strong passwords
- Limit database user permissions
- Enable SSL connections if possible
- Regular backups

## Static File Optimization

### CDN Configuration
- Bootstrap 5.3.3 from jsDelivr
- Font Awesome 6.4.0 from Cloudflare
- Select2 from jsDelivr
- Local fallbacks configured

### Asset Caching
- 1-year cache headers for static assets
- Gzip compression enabled
- Asset integrity verification

## Deployment Steps

### 1. Prepare Environment
```bash
# Set production environment
export ENV=production
export ENABLE_TALISMAN=1
export FORCE_HTTPS=1
export FLASK_DEBUG=0
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Database Setup
```bash
# Run migrations
flask db upgrade

# Create initial data if needed
python setup_db.py
```

### 4. Test Configuration
```bash
# Test database connection
python -c "from app import create_app; app = create_app(); print('Database URI:', app.config['SQLALCHEMY_DATABASE_URI'])"

# Test security configuration
python -c "from production_security_config import validate_security_config; from app import create_app; app = create_app(); validate_security_config(app)"
```

### 5. Deploy Application
- Use WSGI server (Gunicorn, uWSGI, etc.)
- Configure reverse proxy (Nginx, Apache)
- Set up SSL certificates
- Configure monitoring

## Monitoring and Maintenance

### Log Monitoring
- Monitor error logs for issues
- Track security events
- Monitor database performance
- Watch for unusual activity

### Regular Tasks
- Update dependencies
- Backup database
- Rotate logs
- Security audits

## Performance Optimization

### Database Optimization
- Connection pooling configured
- Query optimization
- Regular maintenance

### Application Optimization
- Static asset caching
- Database query caching
- Session management

## Troubleshooting

### Common Issues
1. **Database Connection**: Check DATABASE_URL and credentials
2. **Security Headers**: Verify ENABLE_TALISMAN=1
3. **Static Files**: Check file permissions and paths
4. **OAuth**: Verify client IDs and secrets

### Debug Mode
Never enable DEBUG mode in production. Use logs for troubleshooting.

## Support

For deployment issues:
1. Check logs in `logs/` directory
2. Verify environment variables
3. Test database connectivity
4. Review security configuration
