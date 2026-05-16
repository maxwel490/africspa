# --- MULTI-TENANT AUTHENTICATION ---

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Worker, Salon, db
from app.auth import auth_bp
from sqlalchemy import or_

def get_salon_by_slug(salon_slug):
    """Get salon by slug for subdomain routing"""
    return Salon.query.filter_by(slug=salon_slug, is_active=True).first()

def get_salon_for_user(user):
    """Get the salon this user belongs to"""
    return Salon.query.get(user.salon_id) if user.salon_id else None

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Multi-tenant login with salon isolation"""
    if current_user.is_authenticated:
        return redirect_to_dashboard(current_user.role)
    
    # Get salon from subdomain or selection
    salon_slug = request.host.split('.')[0] if '.' in request.host else None
    salon = get_salon_by_slug(salon_slug) if salon_slug else None
    
    if request.method == 'POST':
        login_id = (request.form.get('username') or '').strip()
        password = request.form.get('password')
        salon_selection = request.form.get('salon_id')
        
        # If salon selection provided, use it
        if salon_selection:
            salon = Salon.query.get(salon_selection)
        
        if not salon and not salon_selection:
            flash('Please select your salon', 'danger')
            return render_login_page_with_salons()
        
        # Look for user within the selected salon
        user = Worker.query.filter(
            Worker.salon_id == salon.id,
            or_(
                Worker.username == login_id,
                Worker.email.ilike(login_id)
            )
        ).first()

        if user and user.check_password(password):
            # Additional checks
            if not user.is_active:
                flash('Your account has been deactivated. Please contact your salon administrator.', 'danger')
                return redirect(url_for('auth.login'))
            
            if user.role != 'admin' and not user.branch:
                active_branches = ', '.join([b.name for b in salon.branches.filter_by(is_active=True).all()])
                flash(f"Login failed: Account '{login_id}' is not assigned to a branch ({active_branches}). Please contact your salon Admin.", "danger")
                return redirect(url_for('auth.login'))
            
            # Check salon subscription
            if not salon.is_active:
                flash('Your salon subscription is not active. Please contact support.', 'danger')
                return redirect(url_for('auth.login'))
            
            if salon.subscription_expires and salon.subscription_expires < datetime.utcnow():
                flash('Your salon subscription has expired. Please renew to continue.', 'danger')
                return redirect(url_for('auth.login'))

            login_user(user)
            
            # Store salon info in session
            session['salon_id'] = salon.id
            session['salon_name'] = salon.name
            session['salon_slug'] = salon.slug
            
            branch_info = f" ({user.branch})" if user.branch else " (Global Admin)"
            flash(f'Welcome back, {user.username}!{branch_info}', 'success')
            
            return redirect_to_dashboard(user.role)
        
        flash('Invalid username/email or password.', 'danger')
    
    # If no salon detected, show salon selection
    if not salon:
        return render_login_page_with_salons()
    
    return render_template('auth/login.html', salon=salon)

def render_login_page_with_salons():
    """Render login page with salon selection"""
    salons = Salon.query.filter_by(is_active=True).all()
    return render_template('auth/select_salon.html', salons=salons)

@auth_bp.route('/logout')
@login_required
def logout():
    """Logout and clear salon session"""
    logout_user()
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

def redirect_to_dashboard(role):
    """Role-based redirection within salon context"""
    if role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif role == 'accountant':
        return redirect(url_for('accountant.dashboard'))
    elif role == 'salonist':
        return redirect(url_for('salonist.dashboard'))
    
    return redirect(url_for('auth.login'))

# --- MULTI-TENANT DECORATORS ---

from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

def tenant_required(f):
    """Ensure user belongs to a valid salon"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        salon_id = session.get('salon_id')
        if not salon_id or current_user.salon_id != salon_id:
            flash('Invalid session. Please login again.', 'danger')
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return wrapper

def subscription_required(plan='standard'):
    """Check if salon has valid subscription"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            salon = Salon.query.filter_by(id=current_user.salon_id).first()
            if not salon:
                return redirect(url_for('auth.login'))
            
            # No plan limitations - all features available
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
