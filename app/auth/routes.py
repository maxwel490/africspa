from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Worker, db, Branch, Salon
from app.auth import auth_bp  # Imports from the package's __init__.py
from sqlalchemy import or_

def get_allowed_self_reset_branches():
    """Get list of branch names that allow self-reset"""
    return {branch.name.lower() for branch in Branch.query.filter_by(is_active=True).all()}


def _normalize_phone(phone_value):
    """Keep only digits so minor phone formatting differences do not block resets."""
    return ''.join(ch for ch in (phone_value or '') if ch.isdigit())


def _normalize_id_number(id_value):
    """Normalize ID numbers to avoid mismatch due to spaces/case differences."""
    return ''.join((id_value or '').split()).upper()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handles staff login, branch validation, and role-based redirection."""
    try:
        # If already logged in, send them straight to their dashboard
        if current_user.is_authenticated:
            return redirect_to_dashboard(current_user.role)

        if request.method == 'POST':
            login_id = (request.form.get('username') or '').strip()
            password = request.form.get('password')
            
            # Look for the worker by username OR email
            user = Worker.query.filter(
                or_(
                    Worker.username == login_id,
                    Worker.email.ilike(login_id)
                )
            ).first()
            
            # If no user found by username, try email as username
            if not user:
                user = Worker.query.filter_by(email=login_id).first()

            if user and user.check_password(password):
                # NEW: Branch Safety Check
                # Accountants and Salonists must have an assigned branch to proceed
                # Super Admins and Admins don't require branch assignment
                if user.role not in ['admin', 'superadmin'] and not user.branch:
                    active_branches = ', '.join([b.name for b in Branch.query.filter_by(is_active=True).all()])
                    flash(f"Login failed: Account '{login_id}' is not assigned to a branch ({active_branches}). Please contact the Admin.", "danger")
                    return redirect(url_for('auth.login'))

                login_user(user)
                
                # Enforce access control after login
                try:
                    from app.middleware.login_access_control import enforce_access_after_login, check_login_access
                    access = enforce_access_after_login()
                    
                    # Check if redirect is needed based on access control
                    redirect_check = check_login_access()
                    if redirect_check:
                        return redirect_check
                except Exception as e:
                    # Log error but allow login to continue
                    import logging
                    logging.error(f"Access control error during login: {str(e)}")
                
                # Show branch info in the welcome message if applicable
                branch_info = f" ({user.branch})" if user.branch else " (Global Admin)"
                flash(f'Welcome back, {user.username}!{branch_info}', 'success')
                
                return redirect_to_dashboard(user.role)
            
            # Generic error for security
            flash('Username or password incorrect.', 'danger')
                
        return render_template('auth/login.html')
        
    except Exception as e:
        # Catch any unexpected errors to prevent system crashes
        import logging
        logging.error(f"Login error: {str(e)}")
        flash('An error occurred during login. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
@login_required
def logout():
    """Logs the user out and returns to login page."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Allow salonists to reset their own password after identity verification."""
    if current_user.is_authenticated:
        return redirect_to_dashboard(current_user.role)

    if request.method == 'POST':
        login_id = (request.form.get('username') or '').strip()
        phone = request.form.get('phone') or ''
        id_number = request.form.get('id_number') or ''
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not login_id or not phone or not id_number or not new_password or not confirm_password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        if len(new_password) < 8:
            flash('New password must be at least 8 characters.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        user = Worker.query.filter(
            Worker.role == 'salonist',
            or_(
                Worker.username == login_id,
                Worker.email.ilike(login_id)
            )
        ).first()

        if not user:
            flash('Unable to verify your account details.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        user_branch = (user.branch or '').strip().lower()
        allowed_branches = get_allowed_self_reset_branches()
        if user_branch not in allowed_branches:
            flash('Self-reset is only available for salonists in active branches. Contact your accountant.', 'warning')
            return redirect(url_for('auth.forgot_password'))

        stored_phone = _normalize_phone(user.phone)
        entered_phone = _normalize_phone(phone)
        if not stored_phone or stored_phone != entered_phone:
            flash('Unable to verify your account details.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        stored_id = _normalize_id_number(user.id_number)
        entered_id = _normalize_id_number(id_number)
        if not stored_id or stored_id != entered_id:
            flash('Unable to verify your account details.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        user.set_password(new_password)
        db.session.commit()
        flash('Password reset successful. Please log in with your new password.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')

def redirect_to_dashboard(role):
    """
    Sends the user to the correct blueprint based on their role string.
    Ensures TRM, Ngong, and Nextgen staff land on their isolated dashboards.
    """
    if role == 'superadmin':
        return redirect(url_for('superadmin.dashboard'))
    elif role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif role == 'accountant':
        # The accountant's routes will further filter data by current_user.branch
        return redirect(url_for('accountant.dashboard'))
    elif role == 'salonist':
        return redirect(url_for('salonist.dashboard'))
    
    return redirect(url_for('auth.login'))