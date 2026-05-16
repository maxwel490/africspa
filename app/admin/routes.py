from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from app.models import Expense, Service, Worker, Appointment, Product, ProductTransaction, SupplierInvoice, MonthlyReconciliation, DepartmentCategoryConfig, Branch, ServiceOrder, db 
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from app.models import Salon, Worker, Branch, Client, Appointment, ServiceOrder, Product, db
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from app.middleware.access_control_middleware import access_control_middleware, billing_redirect, service_orders_only, no_services_access, no_inventory_access
from app.decorators import roles_required
from app.admin import admin_bp
import random
from app.services.chat_service import ChatService
from app.models import Message


def get_managed_branches():
    try:
        existing = Branch.query.order_by(Branch.name.asc()).all()
        return [b.name for b in existing if b.is_active]
    except Exception:
        db.session.rollback()
        return []

@admin_bp.route('/chat-support')
@login_required
@roles_required('admin')
def chat_support():
    """Tenant admin chat support interface"""
    # Get messages for this admin
    messages = db.session.query(Message).filter(
        (Message.recipient_id == current_user.id) | (Message.sender_id == current_user.id)
    ).order_by(Message.created_at.desc()).limit(50).all()
    
    # Get unread count
    unread_count = db.session.query(Message).filter(
        Message.recipient_id == current_user.id,
        Message.is_read == False
    ).count()
    
    # Group messages by conversation
    conversations = {}
    for msg in messages:
        key = msg.session_id or f"direct_{msg.sender_id if msg.sender_id != current_user.id else msg.recipient_id}"
        if key not in conversations:
            conversations[key] = []
        # Convert Message object to dictionary for JSON serialization
        conversations[key].append({
            'id': msg.id,
            'content': msg.content,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'sender_role': msg.sender_role,
            'recipient_id': msg.recipient_id,
            'recipient_name': msg.recipient_name,
            'recipient_role': msg.recipient_role,
            'session_id': msg.session_id,
            'is_read': msg.is_read,
            'created_at': msg.created_at.isoformat()
        })
    
    # Sort messages within each conversation chronologically (oldest first, newest last)
    for key in conversations:
        conversations[key].sort(key=lambda x: x['created_at'])
    
    return render_template('admin/chat_support.html', 
                        conversations=conversations,
                        messages=messages,
                        unread_count=unread_count)

@admin_bp.route('/chat/send', methods=['POST'])
@login_required
@roles_required('admin')
def admin_send_chat_message():
    """Send message from admin to superadmin"""
    try:
        data = request.get_json()
        
        recipient_id = data.get('recipient_id')
        content = data.get('message', '').strip()
        session_id = data.get('session_id', '')
        
        if not content:
            return jsonify({'success': False, 'error': 'Message is required'})
        
        # Get superadmin user
        superadmin = Worker.query.filter_by(role='superadmin').first()
        if not superadmin:
            return jsonify({'success': False, 'error': 'Superadmin not available'})
        
        # Create message from admin to superadmin
        message = ChatService.send_message(
            sender_id=current_user.id,
            recipient_id=superadmin.id,
            content=content,
            sender_name=current_user.full_name,
            recipient_name=superadmin.full_name,
            recipient_role='superadmin',
            session_id=session_id
        )
        
        # Store additional info
        message.sender_role = 'admin'
        message.session_id = session_id
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'sender_name': message.sender_name
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/chat/mark-read', methods=['POST'])
@login_required
@roles_required('admin')
def mark_chat_read():
    """Mark messages as read for admin"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if session_id:
            # Mark messages in this session as read
            messages = Message.query.filter(
                Message.session_id == session_id,
                Message.recipient_id == current_user.id,
                Message.is_read == False
            ).all()
            
            for msg in messages:
                msg.is_read = True
                msg.read_at = datetime.utcnow()
            
            db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.app_context_processor
def inject_managed_branches():
    return {'managed_branches': get_managed_branches()}

@admin_bp.route('/dashboard')
@login_required
@roles_required('admin')
@billing_redirect
def dashboard():
    selected_branch = request.args.get('branch')
    
    # Handle custom date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        # Default to last 30 days
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=29)
    
    # Generate date range
    dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    labels = [d.strftime('%d %b') for d in dates]

    # Base queries for stats
    worker_query = Worker.query.filter(Worker.role != 'superadmin')
    appointment_query = Appointment.query
    if selected_branch:
        worker_query = worker_query.filter_by(branch=selected_branch)
        appointment_query = appointment_query.filter_by(branch=selected_branch)

    # Basic Stats
    total_salonists = worker_query.filter_by(role='salonist').count()
    total_appointments = appointment_query.count()

    # Additional Analytics Stats
    # Total service orders in date range
    service_order_query = ServiceOrder.query.filter(
        ServiceOrder.created_at >= start_date,
        ServiceOrder.created_at <= end_date,
        ServiceOrder.payment_status == 'paid'
    )
    if selected_branch:
        service_order_query = service_order_query.filter_by(branch=selected_branch)
    
    total_service_orders = service_order_query.count()
    
    # Global unique clients (across all branches, not just selected branch)
    global_clients_query = ServiceOrder.query.filter(
        ServiceOrder.created_at >= start_date,
        ServiceOrder.created_at <= end_date,
        ServiceOrder.payment_status == 'paid'
    )
    global_unique_clients = global_clients_query.with_entities(func.count(func.distinct(ServiceOrder.client_id))).scalar() or 0
    
    # Also count by phone number for clients without client_id
    global_unique_clients_by_phone = global_clients_query.filter(ServiceOrder.client_id.is_(None)).with_entities(
        func.count(func.distinct(ServiceOrder.client_phone))
    ).scalar() or 0
    
    # Total global unique clients
    unique_clients = global_unique_clients + global_unique_clients_by_phone
    
    avg_transaction_value = service_order_query.with_entities(func.avg(ServiceOrder.total_amount)).scalar() or 0.0

    pending_invoice_query = db.session.query(func.sum(SupplierInvoice.amount)).filter(
        func.lower(SupplierInvoice.status) == 'pending'
    )
    if selected_branch:
        pending_invoice_query = pending_invoice_query.filter(SupplierInvoice.branch == selected_branch)
    pending_supplier_invoices_total = float(pending_invoice_query.scalar() or 0.0)

    # Revenue Data Logic using Paid Service Orders with Daily Totals
    branch_data = {}
    # Define your branches here
    branches_to_track = get_managed_branches()

    if selected_branch:
        # Single Branch View: One line for the selected branch
        revenue = []
        for d in dates:
            daily_total = db.session.query(func.sum(ServiceOrder.total_amount)).filter(
                func.date(ServiceOrder.created_at) == d,
                ServiceOrder.branch == selected_branch,
                ServiceOrder.payment_status == 'paid'
            ).scalar() or 0.0
            revenue.append(float(daily_total))
        branch_data[selected_branch] = revenue
    else:
        # Global HQ View: Separate line for EVERY branch
        for branch in branches_to_track:
            revenue = []
            for d in dates:
                daily_total = db.session.query(func.sum(ServiceOrder.total_amount)).filter(
                    func.date(ServiceOrder.created_at) == d,
                    ServiceOrder.branch == branch,
                    ServiceOrder.payment_status == 'paid'
                ).scalar() or 0.0
                revenue.append(float(daily_total))
            branch_data[branch] = revenue

    total_revenue_30d = sum(sum(values) for values in branch_data.values())
    peak_daily_revenue = max((max(values) for values in branch_data.values() if values), default=0.0)

    return render_template('admin/dashboard.html', 
                           total_salonists=total_salonists,
                           total_appointments=total_appointments,
                           total_service_orders=total_service_orders,
                           unique_clients=unique_clients,
                           avg_transaction_value=avg_transaction_value,
                           pending_supplier_invoices_total=pending_supplier_invoices_total,
                           total_revenue_30d=total_revenue_30d,
                           peak_daily_revenue=peak_daily_revenue,
                           labels=labels,
                           branch_data=branch_data, # Send dictionary instead of single list
                           selected_branch=selected_branch,
                           datetime=datetime,
                           timedelta=timedelta)


@admin_bp.route('/branches', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def manage_branches():
    selected_branch = request.args.get('branch')

    if request.method == 'POST':
        action = request.form.get('action')
        
        # Handle branch actions
        if action in ['activate', 'deactivate', 'delete']:
            branch_id = request.form.get('branch_id', type=int)
            branch = Branch.query.get_or_404(branch_id)
            
            if action == 'activate':
                branch.is_active = True
                db.session.commit()
                flash(f"Branch '{branch.name}' activated successfully.", 'success')
                
            elif action == 'deactivate':
                branch.is_active = False
                db.session.commit()
                flash(f"Branch '{branch.name}' deactivated successfully.", 'warning')
                
            elif action == 'delete':
                # Check if branch has any dependencies (exclude superadmin)
                workers_count = Worker.query.filter_by(branch=branch.name).filter(Worker.role != 'superadmin').count()
                products_count = Product.query.filter_by(branch=branch.name).count()
                service_orders_count = ServiceOrder.query.filter_by(branch=branch.name).count()
                
                if workers_count > 0 or products_count > 0 or service_orders_count > 0:
                    flash(f"Cannot delete branch '{branch.name}' - it has associated data ({workers_count} workers, {products_count} products, {service_orders_count} service orders).", 'danger')
                else:
                    db.session.delete(branch)
                    db.session.commit()
                    flash(f"Branch '{branch.name}' deleted successfully.", 'success')
        
        # Handle new branch creation
        else:
            branch_name = (request.form.get('name') or '').strip()

            if not branch_name:
                flash('Branch name is required.', 'danger')
                return redirect(url_for('admin.manage_branches', branch=selected_branch) if selected_branch else url_for('admin.manage_branches'))

            existing = Branch.query.filter(func.lower(Branch.name) == branch_name.lower()).first()
            if existing:
                flash(f"Branch '{existing.name}' already exists.", 'warning')
                return redirect(url_for('admin.manage_branches', branch=selected_branch) if selected_branch else url_for('admin.manage_branches'))

            try:
                # Create branch with proper tenant association
                import uuid
                branch_code = f"BR{str(uuid.uuid4())[:8].upper()}"
                new_branch = Branch(
                    name=branch_name,
                    code=branch_code,
                    salon_id=current_user.salon_id,
                    address=f'{branch_name} Branch - Address to be updated',
                    phone=f'Phone for {branch_name} Branch',
                    currency='KES'  # Default currency
                )
                db.session.add(new_branch)
                db.session.commit()
                
                # Branch creation success message
                flash(f"Branch '{branch_name}' added successfully!", 'success')
                    
            except Exception as e:
                db.session.rollback()
                flash(f'Could not add branch. Error: {str(e)}', 'danger')

        return redirect(url_for('admin.manage_branches', branch=selected_branch) if selected_branch else url_for('admin.manage_branches'))

    # Only show branches for the current tenant
    branches = Branch.query.filter_by(salon_id=current_user.salon_id).order_by(Branch.name.asc()).all()
    return render_template('admin/branches.html', branches=branches)

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


@admin_bp.route('/services', methods=['GET', 'POST'])
@admin_bp.route('/services/<int:service_id>', methods=['POST']) # Handles Edit/Delete
@login_required
@roles_required('admin')
@no_services_access
def manage_services(service_id=None):
    def parse_float_field(field_name, default=0.0):
        raw_value = request.form.get(field_name, None)
        if raw_value is None:
            return float(default)
        text = str(raw_value).strip()
        if text == '':
            return float(default)
        return float(text)

    # 1. Determine Action: Are we Deleting?
    action = (request.args.get('action') or request.form.get('action') or '').strip().lower()
    selected_branch = request.args.get('branch') or request.form.get('branch')
    
    target_service_id = service_id or request.form.get('service_id', type=int)

    is_delete_intent = (
        target_service_id is not None and (
            action == 'delete' or
            (request.method == 'POST' and not request.form.get('name') and not request.form.get('category'))
        )
    )

    if is_delete_intent:
        service = Service.query.filter_by(id=target_service_id, salon_id=current_user.salon_id).first_or_404()
        try:
            db.session.delete(service)
            db.session.commit()
            flash(f"Service '{service.name}' deleted.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Cannot delete this service because it is used in existing appointment records.", "danger")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Service delete error: {e}")
            flash("Error deleting service. Please try again.", "danger")
        return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

    # 2. Handle Form Submissions (Create or Edit)
    if request.method == 'POST':
        try:
            # If service_id exists, we are editing; otherwise, creating.
            service = db.session.get(Service, service_id) if service_id else Service()
            if service_id and not service:
                flash("Service not found.", "danger")
                return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))
            
            # Set salon_id for new services (required field)
            if not service_id and not service.salon_id:
                if not current_user.salon_id:
                    flash("No salon associated with user. Cannot create service.", "danger")
                    return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))
                service.salon_id = current_user.salon_id
            
            # Capture inputs
            service.name = request.form.get('name', '').strip()
            service.category = request.form.get('category')

            if not service.name:
                flash("Service name is required.", "danger")
                return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

            if not service.category:
                flash("Service category is required.", "danger")
                return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

            duplicate_query = Service.query.filter(
                func.lower(Service.name) == service.name.lower(),
                Service.salon_id == current_user.salon_id
            )
            if service_id:
                duplicate_query = duplicate_query.filter(Service.id != service_id)
            if duplicate_query.first():
                flash(f"A service named '{service.name}' already exists in your salon.", "danger")
                return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

            service.base_price = parse_float_field('base_price', 0.0)
            selected_is_fixed = (request.form.get('is_fixed_base') or 'true').strip().lower() == 'true'
            
            comm_front = parse_float_field('commission_front', 0.0)
            comm_back = parse_float_field('commission_back', 0.0)

            # 3. Apply Business Logic Branching
            if service.category == 'Hair':
                service.is_fixed_base = selected_is_fixed
                # Keeps raw values (can be Rates or Fixed KSh based on JS)
                service.commission_front = comm_front
                service.commission_back = comm_back
            
            elif service.category == 'Special Hair':
                service.is_fixed_base = selected_is_fixed
                # Both are rates (e.g., 0.25)
                service.commission_front = comm_front
                service.commission_back = comm_back
                
            else:
                service.is_fixed_base = selected_is_fixed
                # Non-Hair: comm_front is a rate, back is forced to 0
                service.commission_front = comm_front
                service.commission_back = 0.0

            if not service_id:
                db.session.add(service)
            
            db.session.commit()
            flash(f"Service '{service.name}' saved successfully!", "success")
            
        except ValueError:
            db.session.rollback()
            flash("Error processing service: Ensure all values are numeric.", "danger")
        except IntegrityError:
            db.session.rollback()
            flash("Service could not be saved due to duplicate or invalid data.", "danger")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Service save error: {e}")
            flash("Error processing service. Please try again.", "danger")
            
        return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

    # 3. GET: Fetch and display list
    services = Service.query.filter_by(salon_id=current_user.salon_id).order_by(Service.category, Service.name).all()
    
    # Get salon's currency for pricing display
    salon_currency = 'KES'  # Default
    if current_user.salon_id:
        from app.models import Salon
        salon = Salon.query.get(current_user.salon_id)
        if salon and salon.currency:
            salon_currency = salon.currency
    
    return render_template('admin/services.html', services=services, salon_currency=salon_currency)



@admin_bp.route('/product-costs')
@login_required
@roles_required('admin')
def product_costs():
    """Sums product_cost, fetches utilities, and AUTO-FETCHES stock invoices."""
    selected_branch = request.args.get('branch')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    category_inputs = {
        'wash': '',
        'nails': '',
        'makeup': '',
        'extensions': ''
    }

    # 1. Date handling
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    else:
        start_date = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)

    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    else:
        end_date = datetime.utcnow()

    # 2. Branch Normalization
    db_branch = selected_branch
    if selected_branch and " Branch" in selected_branch:
        db_branch = selected_branch.replace(" Branch", "")

    category_branch_key = db_branch or 'Global'

    existing_configs = DepartmentCategoryConfig.query.filter_by(branch=category_branch_key).all()
    for cfg in existing_configs:
        key = (cfg.department or '').strip().lower()
        if key in category_inputs:
            category_inputs[key] = cfg.categories_text or ''

    category_arg_map = {
        'wash': 'wash_categories',
        'nails': 'nails_categories',
        'makeup': 'makeup_categories',
        'extensions': 'extensions_categories'
    }
    submitted_any_category = any(arg_name in request.args for arg_name in category_arg_map.values())

    if submitted_any_category:
        for dept_key, arg_name in category_arg_map.items():
            if arg_name not in request.args:
                continue
            value = (request.args.get(arg_name) or '').strip()
            config_row = DepartmentCategoryConfig.query.filter_by(
                branch=category_branch_key,
                department=dept_key
            ).first()
            if not config_row:
                config_row = DepartmentCategoryConfig(
                    branch=category_branch_key,
                    department=dept_key,
                    categories_text=value
                )
                db.session.add(config_row)
            else:
                config_row.categories_text = value
            category_inputs[dept_key] = value
        db.session.commit()
        flash('Department categories saved successfully.', 'success')

    # --- 3. FETCH UTILITY EXPENSES ---
    water_query = db.session.query(func.sum(Expense.amount)).filter(
        Expense.category == 'Water',
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date
    )
    electric_query = db.session.query(func.sum(Expense.amount)).filter(
        Expense.category == 'Power',
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date
    )
    if db_branch:
        water_query = water_query.filter(Expense.branch == db_branch)
        electric_query = electric_query.filter(Expense.branch == db_branch)

    water_total = water_query.scalar() or 0.0
    electric_total = electric_query.scalar() or 0.0

    # --- 4. NEW: FETCH STOCK INVOICES PER DEPARTMENT ---
    # This pulls from the ProductTransaction table we updated earlier
    stk_query = db.session.query(
        ProductTransaction.department,
        func.sum(ProductTransaction.total_amount),
        func.count(ProductTransaction.id),
        func.max(ProductTransaction.timestamp)
    ).filter(
        ProductTransaction.transaction_type == 'Restock',
        ProductTransaction.timestamp >= start_date,
        ProductTransaction.timestamp <= end_date
    )

    if db_branch:
        # Join with SupplierInvoice to filter by branch if branch is stored there
        stk_query = stk_query.join(SupplierInvoice).filter(SupplierInvoice.branch == db_branch)

    stk_results = stk_query.group_by(ProductTransaction.department).all()
    
    # Map database names to your template keys (lowercase)
    # Ensure your 'department' strings in DB match these (e.g., 'Wash', 'Nails')
    invoice_totals = {'wash': 0, 'nails': 0, 'makeup': 0, 'extensions': 0}
    invoice_meta = {
        'wash': {'count': 0, 'last_updated': None},
        'nails': {'count': 0, 'last_updated': None},
        'makeup': {'count': 0, 'last_updated': None},
        'extensions': {'count': 0, 'last_updated': None}
    }
    for dept, total, row_count, last_updated in stk_results:
        clean_dept = (dept or "").strip().lower()
        if 'wash' in clean_dept:
            invoice_totals['wash'] = total or 0
            invoice_meta['wash'] = {'count': int(row_count or 0), 'last_updated': last_updated}
        elif 'nails' in clean_dept:
            invoice_totals['nails'] = total or 0
            invoice_meta['nails'] = {'count': int(row_count or 0), 'last_updated': last_updated}
        elif 'makeup' in clean_dept:
            invoice_totals['makeup'] = total or 0
            invoice_meta['makeup'] = {'count': int(row_count or 0), 'last_updated': last_updated}
        elif 'hair' in clean_dept or 'extension' in clean_dept:
            invoice_totals['extensions'] = total or 0
            invoice_meta['extensions'] = {'count': int(row_count or 0), 'last_updated': last_updated}

    # --- 5. Query completed appointments (Fund Collection) ---
    query = Appointment.query.filter(
        Appointment.status == 'Completed',
        Appointment.appointment_time >= start_date,
        Appointment.appointment_time <= end_date
    )
    if db_branch:
        query = query.filter_by(branch=db_branch)
        
    all_work = query.all()
    totals = {'wash': 0, 'nails': 0, 'makeup': 0, 'extensions': 0, 'grand_total': 0}
    branch_data = {}

    for item in all_work:
        b_name = item.branch or "Unknown"
        if b_name not in branch_data:
            branch_data[b_name] = {'wash': 0, 'nails': 0, 'makeup': 0, 'extensions': 0, 'total': 0}
            
        amount = item.product_cost or 0
        dept = (item.department or "").strip().capitalize()
        service = (item.service_type or "").upper()

        target_key = None
        if dept == 'Wash' or 'WASH' in service: target_key = 'wash'
        elif dept == 'Nails' or 'NAILS' in service: target_key = 'nails'
        elif dept == 'Makeup' or 'MAKE UP' in service or 'MAKEUP' in service: target_key = 'makeup'
        elif dept == 'Hair' or any(x in service for x in ['BRAIDS', 'CORNROWS', 'EXTENSIONS', 'PERM']):
            target_key = 'extensions'

        if target_key:
            totals[target_key] += amount
            branch_data[b_name][target_key] += amount
            branch_data[b_name]['total'] += amount
            totals['grand_total'] += amount
            
    return render_template('admin/inventory_costs.html', 
                           totals=totals, 
                           invoice_totals=invoice_totals, # New variable for template
                           invoice_meta=invoice_meta,
                           category_inputs=category_inputs,
                           branch_data=branch_data,
                           selected_branch=selected_branch,
                           start_date=start_date,
                           end_date=end_date,
                           water_total=water_total,
                           electric_total=electric_total)

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

@admin_bp.route('/service-orders-analysis', methods=['GET'])
@login_required
def service_orders_analysis():
    # 1. Get arguments from the request
    selected_branch = request.args.get('branch')
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    search_query = request.args.get('search_query', '').strip() # Capture search input
    
    # 2. Set default date range
    if start_str and end_str:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').replace(hour=0, minute=0)
        end_date = datetime.strptime(end_str, '%Y-%m-%d').replace(hour=23, minute=59)
    else:
        today = datetime.utcnow()
        start_date = today.replace(day=1, hour=0, minute=0)
        end_date = today.replace(hour=23, minute=59)
    
    # 3. INITIALIZE THE QUERY
    query = ServiceOrder.query.filter(
        ServiceOrder.status == 'paid'
    )
    
    # 4. Apply Filters (Branch and Search)
    if selected_branch and selected_branch != "":
        query = query.filter(ServiceOrder.branch == selected_branch)
        
    if search_query:
        # Filter by Receipt Number or Client Name
        query = query.filter(or_(
            ServiceOrder.receipt_no.ilike(f"%{search_query}%"),
            ServiceOrder.client_name.ilike(f"%{search_query}%")
        ))
    
    # 5. Execute the query
    service_orders = query.order_by(ServiceOrder.created_at.desc()).all()
    
    # 6. Calculations with Null-Safety
    total_revenue = sum((order.total_amount or 0) for order in service_orders)
    total_commissions = 0  # Service orders don't have commissions in this context
    total_tips = 0  # Service orders don't have tips in this context
    net_profit = total_revenue - total_commissions
    
    return render_template('admin/service_orders_analysis.html', 
                           service_orders=service_orders,
                           start_date=start_date,
                           end_date=end_date,
                           total_revenue=total_revenue,
                           total_commissions=total_commissions,
                           total_tips=total_tips,
                           net_profit=net_profit,
                           search_query=search_query) # Pass back to keep search box filled

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
    






@admin_bp.route('/stock-control', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
@no_inventory_access
def stock_control():
    branch = request.args.get('branch', 'All')
    managed_branches = get_managed_branches()

    def generate_sku(name, category, department, branch):
        """Generate a unique SKU for a product"""
        import re
        import uuid
        
        # Clean and normalize name
        name_clean = re.sub(r'[^a-zA-Z0-9]', '', name.upper())[:8]
        category_clean = re.sub(r'[^a-zA-Z0-9]', '', category.upper())[:3]
        department_clean = re.sub(r'[^a-zA-Z0-9]', '', department.upper())[:3]
        branch_clean = re.sub(r'[^a-zA-Z0-9]', '', branch.upper())[:3]
        
        # Generate base SKU
        base_sku = f"{department_clean}-{category_clean}-{name_clean}-{branch_clean}"
        
        # Add unique identifier if needed
        unique_id = str(uuid.uuid4())[:4].upper()
        sku = f"{base_sku}-{unique_id}"
        
        return sku[:50]  # Ensure it fits in the database field

    # One-time cleanup for legacy dummy/test records
    dummy_items = Product.query.filter(Product.name.ilike('%dummy%')).all()
    if dummy_items:
        for item in dummy_items:
            db.session.delete(item)
        db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_global_item':
            name = (request.form.get('name') or '').strip()
            item_type = (request.form.get('item_type') or '').strip().title()
            department = (request.form.get('department') or '').strip().title()
            quantity = request.form.get('quantity', type=int) or 0
            posted_unit_price = request.form.get('unit_price', type=float)

            requires_selling_price = (item_type == 'Shop') or (item_type == 'Salon' and department == 'Hair')
            unit_price = float(posted_unit_price or 0.0) if requires_selling_price else 0.0

            if not name or item_type not in ['Salon', 'Shop'] or department not in ['Wash', 'Hair', 'Nails', 'Makeup']:
                flash('Provide valid item details (name, type, department).', 'danger')
                return redirect(url_for('admin.stock_control', branch=branch))

            if quantity < 0 or unit_price < 0:
                flash('Quantity and price must be non-negative.', 'danger')
                return redirect(url_for('admin.stock_control', branch=branch))

            created_count = 0
            updated_count = 0
            for target_branch in managed_branches:
                existing = Product.query.filter_by(
                    branch=target_branch,
                    name=name,
                    category=item_type,
                    department=department
                ).first()

                if existing:
                    existing.stock_quantity = (existing.stock_quantity or 0) + quantity
                    existing.unit_price = unit_price
                    if not existing.buying_price or existing.buying_price <= 0:
                        existing.buying_price = unit_price
                    updated_count += 1
                else:
                    # Generate SKU for new product
                    sku = generate_sku(name, item_type, department, target_branch)
                    
                    # Map item_type to inventory_type
                    inventory_type = 'shop' if item_type == 'Shop' else 'salon'
                    
                    db.session.add(Product(
                        name=name,
                        sku=sku,
                        category=item_type,
                        department=department,
                        stock_quantity=quantity,
                        unit_price=unit_price,
                        buying_price=unit_price,
                        reorder_point=5,
                        branch=target_branch,
                        salon_id=current_user.salon_id,
                        inventory_type=inventory_type
                    ))
                    created_count += 1

            db.session.commit()
            flash(f'Item synced across branches. Created: {created_count}, Updated: {updated_count}.', 'success')
            return redirect(url_for('admin.stock_control', branch=branch))

        if action == 'adjust_stock':
            product_id = request.form.get('product_id', type=int)
            quantity = request.form.get('quantity', type=int)
            new_unit_price = request.form.get('unit_price', type=float)

            product = Product.query.get_or_404(product_id)
            if quantity is None or quantity < 0:
                flash('Enter a valid stock quantity (0 or more).', 'danger')
                return redirect(url_for('admin.stock_control', branch=branch))

            requires_selling_price = (
                (product.category or '').strip().title() == 'Shop' or
                ((product.category or '').strip().title() == 'Salon' and (product.department or '').strip().title() == 'Hair')
            )

            if requires_selling_price:
                if new_unit_price is None or new_unit_price < 0:
                    flash('Enter a valid selling price (0 or more).', 'danger')
                    return redirect(url_for('admin.stock_control', branch=branch))
                product.unit_price = float(new_unit_price)
            else:
                product.unit_price = 0.0

            product.stock_quantity = quantity
            db.session.commit()
            if requires_selling_price:
                flash(f'Stock and selling price updated for {product.name} ({product.branch}).', 'info')
            else:
                flash(f'Stock updated for {product.name} ({product.branch}). Selling price remains N/A for this department.', 'info')
            return redirect(url_for('admin.stock_control', branch=branch))

    query = Product.query
    if branch != 'All':
        query = query.filter_by(branch=branch)
    else:
        query = query.filter(Product.branch.in_(managed_branches))

    products = query.order_by(Product.name.asc(), Product.branch.asc()).all()
    used_map = {
        row[0]: int(row[1] or 0)
        for row in db.session.query(ProductTransaction.product_id, func.sum(ProductTransaction.quantity))
        .group_by(ProductTransaction.product_id)
        .all()
    }

    product_data = []
    for product in products:
        used_stock = used_map.get(product.id, 0)
        product_data.append({
            'product': product,
            'used_stock': used_stock,
            'remaining_stock': product.stock_quantity or 0
        })

    return render_template(
        'admin/stock_control.html',
        product_data=product_data,
        branch=branch,
        managed_branches=managed_branches
    )

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def salon_settings():
    """Salon settings and subscription info"""
    from app.models import Salon
    
    # Get current user's salon
    salon = Salon.query.filter_by(id=current_user.salon_id).first() if current_user.salon_id else None
    
    if not salon:
        flash('Salon not found.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'toggle_internal_shop':
            salon.has_internal_shop = not salon.has_internal_shop
            
            # Set default shop commission rate when enabling
            if salon.has_internal_shop and (not salon.shop_commission_rate or salon.shop_commission_rate <= 0):
                salon.shop_commission_rate = 10.0  # Default 10% commission rate
            
            db.session.commit()
            
            status = "enabled" if salon.has_internal_shop else "disabled"
            flash(f"Internal shop {status} successfully", "success")
            
        elif action == 'toggle_service_rectification':
            salon.enable_service_rectification = not salon.enable_service_rectification
            
            db.session.commit()
            
            status = "enabled" if salon.enable_service_rectification else "disabled"
            flash(f"Service rectification {status} successfully", "success")
            
        elif action == 'update_shop_commission':
            commission_rate = request.form.get('shop_commission_rate', type=float)
            
            if commission_rate is not None and commission_rate >= 0 and commission_rate <= 100:
                salon.shop_commission_rate = commission_rate
                db.session.commit()
                flash(f"Shop commission rate updated to {commission_rate}%", "success")
            else:
                flash("Invalid commission rate. Please enter a value between 0 and 100.", "danger")
        
        elif action == 'toggle_backbar':
            salon.has_backbar = not salon.has_backbar
            db.session.commit()
            
            status = "enabled" if salon.has_backbar else "disabled"
            flash(f"Backbar deductions {status} successfully", "success")
        
        elif action == 'save_payment_config':
            # Get enabled payment methods from form
            enabled_methods = []
            default_method = request.form.get('default_method')
            
            # All possible payment methods
            all_methods = [
                {'code': 'mpesa', 'name': 'M-Pesa', 'icon': 'fas fa-mobile-alt'},
                {'code': 'bank', 'name': 'Bank', 'icon': 'fas fa-university'},
                {'code': 'cash', 'name': 'Cash', 'icon': 'fas fa-money-bill'},
                {'code': 'model', 'name': 'Model (No Payment)', 'icon': 'fas fa-user'},
            ]
            
            for method in all_methods:
                if request.form.get(f'enable_{method["code"]}'):
                    enabled_methods.append({
                        'code': method['code'],
                        'name': request.form.get(f'name_{method["code"]}', method['name']),
                        'icon': request.form.get(f'icon_{method["code"]}', method['icon']),
                        'is_default': method['code'] == default_method
                    })
            
            # Save configuration
            import json
            payment_config = {
                'enabled_methods': enabled_methods
            }
            
            salon.payment_config = json.dumps(payment_config)
            db.session.commit()
            flash('Payment configuration saved successfully!', 'success')
        
        return redirect(url_for('admin.salon_settings'))
    
    # Get current payment configuration
    from app.accountant.routes import get_tenant_payment_options
    payment_options = get_tenant_payment_options(current_user.salon_id)
    
    # Get all possible methods for the form
    all_methods = [
        {'code': 'mpesa', 'name': 'M-Pesa', 'icon': 'fas fa-mobile-alt'},
        {'code': 'bank', 'name': 'Bank', 'icon': 'fas fa-university'},
        {'code': 'cash', 'name': 'Cash', 'icon': 'fas fa-money-bill'},
        {'code': 'model', 'name': 'Model (No Payment)', 'icon': 'fas fa-user'},
    ]
    
    # Mark which methods are currently enabled
    enabled_codes = [opt['code'] for opt in payment_options]
    
    # Get backbar groups for this salon
    from app.models import BackbarGroup, Worker
    backbar_groups = BackbarGroup.query.filter_by(salon_id=current_user.salon_id, is_active=True).all()
    
    # Build target groups data
    target_groups = []
    for group in backbar_groups:
        eligible_workers = group.get_eligible_workers(current_user.branch)
        target_groups.append({
            'id': group.id,
            'name': group.name,
            'description': group.description,
            'specialties': group.get_target_specialties(),
            'employment_types': group.get_target_employment_types(),
            'workers': eligible_workers,
            'icon': group.icon,
            'color': group.color
        })
    
    return render_template('admin/salon_settings.html', 
                         salon=salon,
                         payment_options=payment_options,
                         all_methods=all_methods,
                         enabled_codes=enabled_codes,
                         backbar_groups=backbar_groups,
                         target_groups=target_groups)


@admin_bp.route('/backbar-groups')
@login_required
@roles_required('admin')
def backbar_groups():
    """Manage backbar deduction groups"""
    from app.models import BackbarGroup, Worker
    
    salon = Salon.query.filter_by(id=current_user.salon_id).first() if current_user.salon_id else None
    if not salon:
        flash('No salon associated with your account.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    groups = BackbarGroup.query.filter_by(salon_id=salon.id, is_active=True).order_by(BackbarGroup.name).all()
    
    # Get available specialties and employment types for this salon
    workers = Worker.query.filter_by(salon_id=salon.id, role='salonist').all()
    specialties = list(set([w.specialty for w in workers if w.specialty]))
    employment_types = list(set([w.employment_type for w in workers if w.employment_type]))
    
    return render_template('admin/backbar_groups.html', 
                          groups=groups, 
                          salon=salon,
                          specialties=specialties,
                          employment_types=employment_types)


@admin_bp.route('/backbar-groups/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def add_backbar_group():
    """Add a new backbar group"""
    from app.models import BackbarGroup
    
    salon = Salon.query.filter_by(id=current_user.salon_id).first() if current_user.salon_id else None
    if not salon:
        flash('No salon associated with your account.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        target_specialties = request.form.getlist('target_specialties')
        target_employment_types = request.form.getlist('target_employment_types')
        color = request.form.get('color', 'primary')
        icon = request.form.get('icon', 'bi-people')
        
        if not name:
            flash('Group name is required.', 'danger')
            return redirect(url_for('admin.add_backbar_group'))
        
        # Check if group name already exists for this salon
        existing_group = BackbarGroup.query.filter_by(salon_id=salon.id, name=name).first()
        if existing_group:
            flash('A group with this name already exists.', 'danger')
            return redirect(url_for('admin.add_backbar_group'))
        
        new_group = BackbarGroup(
            salon_id=salon.id,
            name=name,
            description=description,
            color=color,
            icon=icon
        )
        
        # Set target specialties and employment types
        if target_specialties:
            new_group.set_target_specialties(target_specialties)
        if target_employment_types:
            new_group.set_target_employment_types(target_employment_types)
        
        try:
            db.session.add(new_group)
            db.session.commit()
            flash(f'Backbar group "{name}" created successfully.', 'success')
            return redirect(url_for('admin.backbar_groups'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating backbar group. Please try again.', 'danger')
    
    # Get available options for form
    from app.models import Worker
    workers = Worker.query.filter_by(salon_id=salon.id, role='salonist').all()
    specialties = list(set([w.specialty for w in workers if w.specialty]))
    employment_types = list(set([w.employment_type for w in workers if w.employment_type]))
    
    return render_template('admin/add_backbar_group.html',
                          specialties=specialties,
                          employment_types=employment_types)


@admin_bp.route('/backbar-groups/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def edit_backbar_group(group_id):
    """Edit a backbar group"""
    from app.models import BackbarGroup
    
    group = BackbarGroup.query.get_or_404(group_id)
    
    # Check if user owns this group
    if group.salon_id != current_user.salon_id:
        flash('You do not have permission to edit this group.', 'danger')
        return redirect(url_for('admin.backbar_groups'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        target_specialties = request.form.getlist('target_specialties')
        target_employment_types = request.form.getlist('target_employment_types')
        color = request.form.get('color', 'primary')
        icon = request.form.get('icon', 'bi-people')
        
        if not name:
            flash('Group name is required.', 'danger')
            return redirect(url_for('admin.edit_backbar_group', group_id=group_id))
        
        # Check if group name already exists (excluding this group)
        existing_group = BackbarGroup.query.filter(
            BackbarGroup.salon_id == group.salon_id,
            BackbarGroup.name == name,
            BackbarGroup.id != group_id
        ).first()
        if existing_group:
            flash('A group with this name already exists.', 'danger')
            return redirect(url_for('admin.edit_backbar_group', group_id=group_id))
        
        group.name = name
        group.description = description
        group.color = color
        group.icon = icon
        
        # Update target specialties and employment types
        group.set_target_specialties(target_specialties)
        group.set_target_employment_types(target_employment_types)
        
        try:
            db.session.commit()
            flash(f'Backbar group "{name}" updated successfully.', 'success')
            return redirect(url_for('admin.backbar_groups'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating backbar group. Please try again.', 'danger')
    
    # Get available options for form
    from app.models import Worker
    workers = Worker.query.filter_by(salon_id=group.salon_id, role='salonist').all()
    specialties = list(set([w.specialty for w in workers if w.specialty]))
    employment_types = list(set([w.employment_type for w in workers if w.employment_type]))
    
    return render_template('admin/edit_backbar_group.html',
                          group=group,
                          specialties=specialties,
                          employment_types=employment_types)


@admin_bp.route('/backbar-groups/<int:group_id>/delete', methods=['POST'])
@login_required
@roles_required('admin')
def delete_backbar_group(group_id):
    """Delete a backbar group"""
    from app.models import BackbarGroup
    
    group = BackbarGroup.query.get_or_404(group_id)
    
    # Check if user owns this group
    if group.salon_id != current_user.salon_id:
        flash('You do not have permission to delete this group.', 'danger')
        return redirect(url_for('admin.backbar_groups'))
    
    # Check if there are any deductions associated with this group
    if group.deductions:
        flash('Cannot delete group that has associated deductions.', 'danger')
        return redirect(url_for('admin.backbar_groups'))
    
    try:
        db.session.delete(group)
        db.session.commit()
        flash(f'Backbar group "{group.name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting backbar group. Please try again.', 'danger')
    
    return redirect(url_for('admin.backbar_groups'))

@admin_bp.route('/payment-settings', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def payment_settings():
    """Manage tenant payment configuration"""
    # Import the payment functions from accountant routes
    from app.accountant.routes import get_tenant_payment_options, save_tenant_payment_config
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_config':
            # Get enabled payment methods from form
            enabled_methods = []
            default_method = request.form.get('default_method')
            
            # All possible payment methods
            all_methods = [
                {'code': 'mpesa', 'name': 'M-Pesa', 'icon': 'fas fa-mobile-alt'},
                {'code': 'bank', 'name': 'Bank', 'icon': 'fas fa-university'},
                {'code': 'cash', 'name': 'Cash', 'icon': 'fas fa-money-bill'},
                {'code': 'model', 'name': 'Model (No Payment)', 'icon': 'fas fa-user'},
            ]
            
            for method in all_methods:
                if request.form.get(f'enable_{method["code"]}'):
                    enabled_methods.append({
                        'code': method['code'],
                        'name': request.form.get(f'name_{method["code"]}', method['name']),
                        'icon': request.form.get(f'icon_{method["code"]}', method['icon']),
                        'is_default': method['code'] == default_method
                    })
            
            # Save configuration
            payment_config = {
                'enabled_methods': enabled_methods
            }
            
            if save_tenant_payment_config(current_user.salon_id, payment_config):
                flash('Payment configuration saved successfully!', 'success')
            else:
                flash('Error saving payment configuration.', 'danger')
            
            return redirect(url_for('admin.payment_settings'))
    
    # Get current configuration
    current_options = get_tenant_payment_options(current_user.salon_id)
    
    # Get all possible methods for the form
    all_methods = [
        {'code': 'mpesa', 'name': 'M-Pesa', 'icon': 'fas fa-mobile-alt'},
        {'code': 'bank', 'name': 'Bank', 'icon': 'fas fa-university'},
        {'code': 'cash', 'name': 'Cash', 'icon': 'fas fa-money-bill'},
        {'code': 'model', 'name': 'Model (No Payment)', 'icon': 'fas fa-user'},
    ]
    
    # Mark which methods are currently enabled
    enabled_codes = [opt['code'] for opt in current_options]
    
    return render_template('admin/payment_settings.html',
                         current_options=current_options,
                         all_methods=all_methods,
                         enabled_codes=enabled_codes)


@admin_bp.route('/chat')
@login_required
@roles_required('admin')
def chat():
    """Chat interface for admin users to contact superadmin"""
    # Get conversation for current user
    messages = ChatService.get_conversation(current_user.id, limit=50)
    unread_count = ChatService.get_unread_count(current_user.id)
    
    # Mark messages as read
    for message in messages:
        if message.recipient_id == current_user.id and not message.is_read:
            ChatService.mark_as_read(message.id)
    
    return render_template('admin/chat.html', 
                        messages=messages, 
                        unread_count=unread_count)


@admin_bp.route('/chat/send', methods=['POST'])
@login_required
@roles_required('admin')
def send_chat_message():
    """Send a message to superadmin"""
    try:
        # Get JSON data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data received'})
        
        content = data.get('message', '').strip()
        session_id = data.get('session_id')
        
        if not content:
            return jsonify({'success': False, 'error': 'Message cannot be empty'})
        
        # Get superadmin user (assuming first superadmin)
        superadmin = Worker.query.filter_by(role='superadmin').first()
        
        if not superadmin:
            return jsonify({'success': False, 'error': 'Superadmin not found in system. Please create a superadmin account first.'})
        
        # Validate superadmin has valid ID for foreign key constraint
        if not superadmin.id:
            return jsonify({'success': False, 'error': 'Superadmin account has invalid ID'})
        
        # Import ChatService to avoid circular imports
        from app.services.chat_service import ChatService
        
        try:
            message = ChatService.send_message(
                sender_id=current_user.id,
                recipient_id=superadmin.id,
                content=content,
                sender_name=current_user.full_name,
                sender_email=current_user.email,
                sender_role='admin',
                recipient_name=superadmin.full_name,
                recipient_role='superadmin',
                session_id=session_id
            )
        except Exception as db_error:
            import logging
            logging.error(f"Database error in ChatService.send_message: {str(db_error)}", exc_info=True)
            
            # Handle specific database errors
            error_msg = str(db_error)
            if "IntegrityError" in error_msg or "foreign key constraint" in error_msg.lower():
                return jsonify({'success': False, 'error': 'Database constraint error: Invalid user reference or missing required data'})
            elif "1080" in error_msg:
                return jsonify({'success': False, 'error': 'Foreign key constraint violation: Superadmin user may not exist or be invalid'})
            else:
                return jsonify({'success': False, 'error': f'Database error: {str(db_error)}'})
        
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'created_at': message.created_at.isoformat(),
                'sender_name': message.sender_name
            }
        })
    
    except Exception as e:
        import logging
        logging.error(f"Error in admin chat send: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'})
