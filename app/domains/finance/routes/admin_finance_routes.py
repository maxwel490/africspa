"""Finance routes: reports, overheads, reconciliation, staff mgmt (admin_bp)."""
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import (Expense, Worker, Appointment, MonthlyReconciliation, db,
                        Product, ProductTransaction, SupplierInvoice, Branch, ServiceOrder)
from sqlalchemy import func
from datetime import datetime, timedelta
from app.decorators import roles_required
from app.admin import admin_bp
import random


def get_managed_branches():
    try:
        existing = Branch.query.order_by(Branch.name.asc()).all()
        return [b.name for b in existing if b.is_active]
    except Exception:
        db.session.rollback()
        return []


@admin_bp.route('/finance')
@login_required
@roles_required('admin')
def finance_report():
    """True Profit calculation using static table values for Cut and Surplus."""
    selected_branch = request.args.get('branch')
    if not selected_branch:
        flash("Please select a branch to view the finance report.", "info")
        return redirect(url_for('admin.dashboard'))

    # Time scopes
    now = datetime.utcnow()
    current_month = now.month
    current_year = now.year
    month_name = now.strftime('%B %Y')
    start_of_week = now - timedelta(days=now.weekday())

    # 1. Monthly Gross Revenue (Total Cost from clients)
    monthly_rev = db.session.query(func.sum(Appointment.total_cost)).filter(
        Appointment.branch == selected_branch,
        func.extract('month', Appointment.appointment_time) == current_month,
        func.extract('year', Appointment.appointment_time) == current_year
    ).scalar() or 0.0

    # 2. Fetch static Salon Cut and Salon Surplus from the table
    # This addresses your requirement to take the amount exactly as recorded
    res_base = db.session.query(
        func.sum(Appointment.salon_cut).label('total_cut'),
        func.sum(Appointment.salon_surplus).label('total_surplus')
    ).filter(
        Appointment.branch == selected_branch,
        func.extract('month', Appointment.appointment_time) == current_month,
        func.extract('year', Appointment.appointment_time) == current_year
    ).first()

    # Safety: Use 'or 0.0' to prevent NoneType addition errors
    total_cut = res_base.total_cut or 0.0
    total_surplus = res_base.total_surplus or 0.0
    base_revenue = total_cut + total_surplus

    # 3. Weekly Revenue
    weekly_rev = db.session.query(func.sum(Appointment.total_cost)).filter(
        Appointment.branch == selected_branch,
        Appointment.appointment_time >= start_of_week
    ).scalar() or 0.0

    # 4. Commissions (Stored for display in the P&L)
    commissions = db.session.query(func.sum(Appointment.commission_earned)).filter(
        Appointment.branch == selected_branch,
        func.extract('month', Appointment.appointment_time) == current_month,
        func.extract('year', Appointment.appointment_time) == current_year
    ).scalar() or 0.0

    # 5. Overheads (Excluding Model Expenses as they are already in total_surplus)
    other_overheads = db.session.query(func.sum(Expense.amount)).filter(
        Expense.branch == selected_branch,
        Expense.category != "Internal/Model Service",
        func.extract('month', Expense.expense_date) == current_month,
        func.extract('year', Expense.expense_date) == current_year
    ).scalar() or 0.0
    
    # Model expenses specifically for the "Marketing" display line
    model_expenses = db.session.query(func.sum(Expense.amount)).filter(
        Expense.branch == selected_branch,
        Expense.category == "Internal/Model Service",
        func.extract('month', Expense.expense_date) == current_month,
        func.extract('year', Expense.expense_date) == current_year
    ).scalar() or 0.0

    # 6. Salaries
    salaries = db.session.query(func.sum(Worker.base_salary)).filter_by(
        branch=selected_branch
    ).scalar() or 0.0

    # 7. Month-end reconciliation results directed to Finance
    month_end_surplus = db.session.query(func.sum(MonthlyReconciliation.final_diff)).filter(
        MonthlyReconciliation.branch == selected_branch,
        MonthlyReconciliation.final_diff > 0,
        func.extract('month', MonthlyReconciliation.created_at) == current_month,
        func.extract('year', MonthlyReconciliation.created_at) == current_year
    ).scalar() or 0.0

    month_end_deficit_raw = db.session.query(func.sum(MonthlyReconciliation.final_diff)).filter(
        MonthlyReconciliation.branch == selected_branch,
        MonthlyReconciliation.final_diff < 0,
        func.extract('month', MonthlyReconciliation.created_at) == current_month,
        func.extract('year', MonthlyReconciliation.created_at) == current_year
    ).scalar() or 0.0
    month_end_deficit = abs(float(month_end_deficit_raw or 0.0))

    net_month_end_effect = float(month_end_surplus or 0.0) - month_end_deficit

    # 8. Final Profit Calculation
    # Note: Commissions and model product costs are already accounted for in 'total_surplus'
    # during the record_work phase. We only subtract fixed overheads and salaries here.
    true_profit = (base_revenue + net_month_end_effect) - other_overheads - salaries

    # 9. Departmental Adjustment for Template logic
    # (Since base_revenue already includes surplus, we calculate the adjustment part)
    # If surplus is less than salon_cut, it indicates product costs were high.
    dept_adjustment = total_surplus 

    return render_template('admin/finance.html',
                           monthly=monthly_rev,
                           base_revenue=base_revenue, 
                           weekly=weekly_rev,
                           commissions=commissions,
                           model_expenses=model_expenses,
                           overheads=other_overheads, # Ensure this name matches HTML
                           salaries=salaries,
                           month_end_surplus=month_end_surplus,
                           month_end_deficit=month_end_deficit,
                           true_profit=true_profit,
                           dept_adjustment=dept_adjustment,
                           current_month_name=month_name,
                           branch=selected_branch)


@admin_bp.route('/manage-overheads', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def manage_overheads():
    """Admins record overheads for specific branches."""
    selected_branch = request.args.get('branch')
    
    if request.method == 'POST':
        category = request.form.get('category')
        # Skip processing if somehow a 'Model' category is submitted
        if category == 'Model Service Deduction':
            flash("Model deductions are handled internally and cannot be added here.", "warning")
            return redirect(url_for('admin.manage_overheads', branch=selected_branch))

        amount = float(request.form.get('amount') or 0)
        branch = request.form.get('branch') 
        date_str = request.form.get('expense_date')
        
        py_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()
        month_ref = py_date.strftime('%B %Y') 

        new_expense = Expense(
            category=category, 
            amount=amount, 
            expense_date=py_date,
            month=month_ref,
            branch=branch
        )
        db.session.add(new_expense)
        db.session.commit()
        
        flash(f"Recorded KSh {amount:,.2f} for {category} at {branch}.", "success")
        return redirect(url_for('admin.manage_overheads', branch=branch))

    query = Expense.query
    if selected_branch:
        query = query.filter_by(branch=selected_branch)
    
    # We also filter out any old 'Model' entries from the view to keep it clean
    recent_overheads = query.filter(Expense.category != 'Model Service Deduction')\
                            .order_by(Expense.expense_date.desc())\
                            .limit(20).all()
    
    return render_template('admin/overheads.html', 
                           overheads=recent_overheads, 
                           branch=selected_branch)


@admin_bp.route('/save-reconciliation', methods=['POST'])
@login_required
@roles_required('admin')
def save_reconciliation():
    data = request.json
    month_str = data.get('month_year')
    branch = data.get('branch')
    
    for entry in data.get('entries', []):
        recon = MonthlyReconciliation(
            month_year=month_str,
            branch=branch,
            category=entry['category'],
            collected_fund=entry['collected'],
            stock_invoice_total=entry['invoice'],
            utility_share=entry['utility'],
            final_diff=entry['diff'],
            reconciled_by_id=current_user.id
        )
        db.session.add(recon)
    
    db.session.commit()
    return jsonify({"status": "success", "message": "Reconciliation Saved!"})


@admin_bp.route('/staff-management', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def staff_management():
    current_branch = request.args.get('branch')

    if request.method == 'POST':
        action = request.form.get('action')
        worker_id = request.form.get('worker_id')
        worker = db.session.get(Worker, int(worker_id)) if worker_id else None

        if worker:
            if action == 'update_salary':
                worker.base_salary = float(request.form.get('salary') or 0)
                flash(f"Salary updated for {worker.username}", "success")
            
            elif action == 'edit_profile':
                # Update name and role
                worker.username = request.form.get('username')
                worker.role = request.form.get('role')
                worker.base_salary = float(request.form.get('salary') or 0)

                # Allow password change for accountants and admins
                if worker.role in ['accountant', 'admin']:
                    new_password = request.form.get('new_password')
                    confirm_password = request.form.get('confirm_password')
                    if new_password:
                        if new_password != confirm_password:
                            flash("Passwords do not match.", "danger")
                            return redirect(url_for('admin.staff_management', branch=current_branch))
                        else:
                            worker.set_password(new_password)
                            flash(f"Password for {worker.username} updated.", "success")

                flash(f"Profile for {worker.username} updated successfully", "info")

            elif action == 'delete':
                db.session.delete(worker)
                flash(f"Staff member {worker.username} removed", "danger")

            db.session.commit()
        
        return redirect(url_for('admin.staff_management', branch=current_branch))

    # FILTER: Only fetch salaried staff (Admins and Managers), exclude superadmin
    salaried_staff = Worker.query.filter(Worker.role != 'salonist', Worker.role != 'superadmin').all()
    
    return render_template('admin/staff_management.html', staff=salaried_staff)


@admin_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # 1. Check if the new username is already taken by someone else
        existing_user = Worker.query.filter_by(username=new_username).first()
        if existing_user and existing_user.id != current_user.id:
            flash("That username is already taken. Please choose another.", "danger")
            return redirect(url_for('admin.edit_profile'))

        # 2. Update Username
        if new_username:
            current_user.username = new_username

        # 3. Update Password (if provided)
        if new_password:
            if new_password != confirm_password:
                flash("Passwords do not match.", "danger")
                return redirect(url_for('admin.edit_profile'))
            else:
                current_user.set_password(new_password)

        try:
            db.session.commit()
            flash("Profile updated successfully!", "success")
            return redirect(url_for('admin.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash("An error occurred while updating your profile.", "danger")
            
    return render_template('admin/edit_profile.html')


@admin_bp.route('/create-worker', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def create_worker():
    """Allows admins to create workers for specific branches with detailed profiles."""
    if request.method == 'POST':
        role = request.form.get('role')
        specialty = request.form.get('specialty', '').strip()
        
        # Enhanced validation for multi-tenant across Africa
        existing_errors = []
        username_suggestions = []
        
        # Check username conflicts for system users
        username = request.form.get('username', '').strip()
        if role in ['accountant', 'admin'] and username:
            existing_user = Worker.query.filter_by(username=username).first()
            if existing_user:
                existing_errors.append(f"Username '{username}' already exists")
                # Generate unique username suggestions
                base_suggestions = [
                    f"{username}_{request.form.get('branch', '').lower()}",
                    f"{username}_{datetime.utcnow().strftime('%Y')}",
                ]
                
                for suggestion in base_suggestions[:3]:
                    if not Worker.query.filter_by(username=suggestion).first():
                        username_suggestions.append(suggestion)
                
                if username_suggestions:
                    flash(f"Username '{username}' already exists. Try: {', '.join(username_suggestions)}", "warning")
                else:
                    flash(f"Username '{username}' already exists. Please choose a different username.", "danger")
                    return render_template('admin/create_worker.html')
        
        # Check ID conflicts
        id_number = request.form.get('id_number', '').strip()
        if id_number and Worker.query.filter_by(id_number=id_number).first():
            existing_errors.append("ID Number already registered")
        
        # Check email conflicts
        email = request.form.get('email', '').strip()
        if email and Worker.query.filter_by(email=email).first():
            existing_errors.append("Email already registered")

        if existing_errors and not username_suggestions:
            flash("Error: " + ", ".join(existing_errors), "danger")
            return render_template('admin/create_worker.html')
        
        # Initialize the worker with general details common to all roles
        new_worker = Worker(
            full_name=request.form.get('full_name'),
            id_number=id_number,
            phone=request.form.get('phone'),
            email=email,
            branch=request.form.get('branch'),
            role=role,
            base_salary=float(request.form.get('base_salary') or 0),
            salon_id=current_user.salon_id,  # Always set salon_id for tenant users
            created_by_id=current_user.id
        )
        
        # Add specialty for salonists
        if role == 'salonist' and specialty:
            new_worker.specialty = specialty
        elif role == 'salonist':
            flash("Specialty is required for salonists.", "danger")
            return render_template('admin/create_worker.html')

        # Conditional Logic: Username and Password only for Accountants and Admins
        if role in ['accountant', 'admin']:
            password = request.form.get('password')
            
            if not username or not password:
                flash("Username and Password are required for Accountants and Admins.", "danger")
                return render_template('admin/create_worker.html')
            
            try:
                if len(password) < 6:
                    raise ValueError("Password must be at least 6 characters long.")
                new_worker.username = username
                new_worker.set_password(password)
            except ValueError as e:
                flash(str(e), "danger")
                return render_template('admin/create_worker.html')
        else:
            # For non-system users (cleaners, etc.), we can use a unique placeholder 
            # or ID number as a username if the database requires it to be non-null.
            new_worker.username = f"staff_{id_number}"
            new_worker.set_password("Default_No_Login_123!") # Secure but unusable

        try:
            db.session.add(new_worker)
            db.session.commit()
            flash(f"Successfully created {role}: {new_worker.full_name}", "success")
            return redirect(url_for('admin.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash("Error: This National ID, Email, or Username is already registered.", "danger")
            
    return render_template('admin/create_worker.html')


@admin_bp.route('/check-username')
@login_required
@roles_required('admin')
def check_username():
    """API endpoint to check username availability in real-time"""
    username = request.args.get('username', '').strip()
    
    if not username or len(username) < 3:
        return jsonify({'available': False, 'message': 'Username must be at least 3 characters'})
    
    # Check if username exists, but exclude current user
    existing_user = Worker.query.filter_by(username=username).first()
    if existing_user and existing_user.id != current_user.id:
        # Generate Google-style intelligent suggestions
        suggestions = []
        
        # Get current user info for personalized suggestions
        current_user_initial = current_user.username[0].upper() if current_user.username else ''
        current_year = datetime.utcnow().strftime('%Y')
        
        # Google-style suggestion patterns
        suggestion_patterns = [
            f"{username}{current_year}",           # username2024
            f"{username}_{current_year}",          # username_2024
            f"{username}{current_user_initial}",    # usernameJ
            f"{username}_{current_user_initial}",   # username_J
            f"{username}123",                      # username123
            f"{username}_{current_user_initial}{current_year[-2:]}", # username_J24
            f"{username}_{current_year[-2:]}",      # username_24
            f"{current_user_initial}{username}",     # Jusername
            f"{username}_official",                 # username_official
            f"{username}_pro",                      # username_pro
        ]
        
        # Add branch-specific suggestion if available
        branch = request.args.get('branch', '').lower()
        if branch and len(branch) >= 3:
            suggestion_patterns.extend([
                f"{username}_{branch}",
                f"{username}{branch[:3]}",
                f"{branch}_{username}",
            ])
        
        # Check each suggestion for availability
        for suggestion in suggestion_patterns:
            if len(suggestions) >= 5:  # Limit to 5 best suggestions
                break
            
            # Skip if too similar to original or already suggested
            if (suggestion == username or 
                suggestion in suggestions or
                len(suggestion) < 3 or
                len(suggestion) > 20):
                continue
                
            # Check if suggestion is available
            if not Worker.query.filter_by(username=suggestion).first():
                suggestions.append(suggestion)
        
        # If no suggestions available, create generic ones
        if len(suggestions) < 3:
            generic_patterns = [
                f"{username}{random.randint(1, 999)}",
                f"{username}_{random.randint(1, 99)}",
                f"{username}_{current_year[-2:]}{random.randint(1, 9)}",
            ]
            
            for suggestion in generic_patterns:
                if len(suggestions) >= 5:
                    break
                if not Worker.query.filter_by(username=suggestion).first():
                    suggestions.append(suggestion)
        
        return jsonify({
            'available': False, 
            'message': f'Username "{username}" is already taken',
            'suggestions': suggestions
        })
    else:
        return jsonify({'available': True, 'message': 'Username is available'})


@admin_bp.route('/delete-worker/<int:worker_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_worker(worker_id):
    """Permanently removes a staff member from the system."""
    worker = Worker.query.get_or_404(worker_id)

    # Safety Check: Prevent the current Admin from deleting their own account
    if worker.id == current_user.id:
        flash("Action denied: You cannot delete your own administrative account.", "danger")
        return redirect(url_for('admin.manage_staff'))

    try:
        # Check for dependent records (Optional: depending on your business logic)
        # If the worker has processed appointments, you might prefer to 'deactivate' 
        # instead of delete to preserve financial history.
        
        db.session.delete(worker)
        db.session.commit()
        flash(f"Staff member {worker.full_name or worker.username} has been successfully removed.", "success")
    except Exception as e:
        db.session.rollback()
        # This usually triggers if the worker is linked to existing Appointments or StaffDeductions
        flash("Error: Cannot delete this worker because they have existing transaction records. Consider deactivating them instead.", "danger")
    
    return redirect(url_for('admin.manage_staff'))
