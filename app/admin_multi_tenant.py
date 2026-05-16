# --- MULTI-TENANT ADMIN ROUTES ---

from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app.models import db, Salon, Branch, Worker, Client, ServiceOrder, Appointment, Product
from app.admin import admin_bp
from app.auth_multi_tenant import tenant_required, subscription_required
from sqlalchemy import func, and_
from datetime import datetime, timedelta

def get_current_salon():
    """Get current salon from session"""
    return Salon.query.get(session.get('salon_id'))

def get_salon_branches():
    """Get branches for current salon"""
    salon = get_current_salon()
    return Branch.query.filter_by(salon_id=salon.id, is_active=True).all() if salon else []

@admin_bp.route('/dashboard')
@login_required
@tenant_required
@subscription_required()
def dashboard():
    """Multi-tenant dashboard - shows only current salon's data"""
    salon = get_current_salon()
    selected_branch = request.args.get('branch')
    
    # Get only this salon's branches
    branches = get_salon_branches()
    branch_names = [b.name for b in branches]
    
    # Validate selected branch belongs to this salon
    if selected_branch and selected_branch not in branch_names:
        selected_branch = None
    
    # Date range filtering
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=29)
    
    dates = [(start_date + timedelta(days=i)).date() for i in range((end_date - start_date).days + 1)]
    
    # SALON-SPECIFIC QUERIES
    base_query = and_(
        ServiceOrder.salon_id == salon.id,
        ServiceOrder.paid_at >= start_date,
        ServiceOrder.paid_at <= end_date,
        ServiceOrder.status == 'paid'
    )
    
    if selected_branch:
        base_query = and_(base_query, ServiceOrder.branch == selected_branch)
    
    # Service orders for this salon only
    service_order_query = ServiceOrder.query.filter(base_query)
    total_service_orders = service_order_query.count()
    
    # Unique clients for this salon only
    global_clients_query = ServiceOrder.query.filter(
        and_(
            ServiceOrder.salon_id == salon.id,
            ServiceOrder.paid_at >= start_date,
            ServiceOrder.paid_at <= end_date,
            ServiceOrder.status == 'paid'
        )
    )
    global_unique_clients = global_clients_query.with_entities(func.count(func.distinct(ServiceOrder.client_id))).scalar() or 0
    global_unique_clients_by_phone = global_clients_query.filter(ServiceOrder.client_id.is_(None)).with_entities(
        func.count(func.distinct(ServiceOrder.client_phone))
    ).scalar() or 0
    unique_clients = global_unique_clients + global_unique_clients_by_phone
    
    # Average transaction for this salon
    avg_transaction_value = service_order_query.with_entities(func.avg(ServiceOrder.transacted_total)).scalar() or 0.0
    
    # Revenue data for this salon's branches only
    branch_data = {}
    for branch in branches:
        branch_revenue_query = ServiceOrder.query.filter(
            and_(
                ServiceOrder.salon_id == salon.id,
                ServiceOrder.branch == branch.name,
                ServiceOrder.paid_at >= start_date,
                ServiceOrder.paid_at <= end_date,
                ServiceOrder.status == 'paid'
            )
        )
        
        revenue = []
        for date in dates:
            daily_total = branch_revenue_query.filter(
                func.date(ServiceOrder.paid_at) == date
            ).with_entities(func.sum(ServiceOrder.transacted_total)).scalar() or 0.0
            revenue.append(float(daily_total))
        branch_data[branch.name] = revenue
    
    total_revenue_30d = sum(sum(values) for values in branch_data.values())
    peak_daily_revenue = max((max(values) for values in branch_data.values() if values), default=0.0)
    
    # Staff count for this salon only
    total_salonists = Worker.query.filter_by(salon_id=salon.id, role='salonist', is_active=True).count()
    
    # Supplier invoices for this salon only
    pending_invoice_query = db.session.query(func.sum(SupplierInvoice.amount)).filter(
        and_(
            SupplierInvoice.salon_id == salon.id,
            func.lower(SupplierInvoice.status) == 'pending'
        )
    )
    if selected_branch:
        pending_invoice_query = pending_invoice_query.filter(SupplierInvoice.branch == selected_branch)
    pending_supplier_invoices_total = float(pending_invoice_query.scalar() or 0.0)
    
    return render_template('admin/dashboard.html', 
                           total_salonists=total_salonists,
                           total_appointments=total_service_orders,  # Using service orders as appointments
                           total_service_orders=total_service_orders,
                           unique_clients=unique_clients,
                           avg_transaction_value=avg_transaction_value,
                           pending_supplier_invoices_total=pending_supplier_invoices_total,
                           total_revenue_30d=total_revenue_30d,
                           peak_daily_revenue=peak_daily_revenue,
                           labels=[date.strftime('%Y-%m-%d') for date in dates],
                           branch_data=branch_data,
                           selected_branch=selected_branch,
                           salon=salon,
                           branches=branches)

@admin_bp.route('/branches', methods=['GET', 'POST'])
@login_required
@tenant_required
@subscription_required()
def manage_branches():
    """Manage branches for current salon only"""
    salon = get_current_salon()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action in ['activate', 'deactivate', 'delete']:
            branch_id = request.form.get('branch_id', type=int)
            branch = Branch.query.filter_by(id=branch_id, salon_id=salon.id).first_or_404()
            
            if action == 'activate':
                branch.is_active = True
                db.session.commit()
                flash(f"Branch '{branch.name}' activated successfully.", 'success')
                
            elif action == 'deactivate':
                branch.is_active = False
                db.session.commit()
                flash(f"Branch '{branch.name}' deactivated successfully.", 'warning')
                
            elif action == 'delete':
                # Check if branch has dependencies within this salon
                if branch.workers.filter_by(salon_id=salon.id).count() > 0 or \
                   branch.products.filter_by(salon_id=salon.id).count() > 0:
                    flash(f"Cannot delete branch '{branch.name}' - it has associated data.", 'danger')
                else:
                    db.session.delete(branch)
                    db.session.commit()
                    flash(f"Branch '{branch.name}' deleted successfully.", 'success')
        
        else:
            # Add new branch
            branch_name = (request.form.get('name') or '').strip()
            
            if not branch_name:
                flash('Branch name is required.', 'danger')
                return redirect(url_for('admin.manage_branches'))
            
            # Check within this salon only
            existing = Branch.query.filter_by(salon_id=salon.id, name=branch_name).first()
            if existing:
                flash(f"Branch '{existing.name}' already exists in your salon.", 'warning')
                return redirect(url_for('admin.manage_branches'))
            
            # Check subscription limits
            current_branch_count = Branch.query.filter_by(salon_id=salon.id).count()
            if current_branch_count >= salon.max_branches:
                flash(f'You have reached your maximum branch limit ({salon.max_branches}). Upgrade your subscription to add more branches.', 'warning')
                return redirect(url_for('admin.manage_branches'))
            
            try:
                db.session.add(Branch(name=branch_name, salon_id=salon.id))
                db.session.commit()
                flash(f"Branch '{branch_name}' added successfully.", 'success')
            except Exception:
                db.session.rollback()
                flash('Could not add branch. Please try again.', 'danger')
        
        return redirect(url_for('admin.manage_branches'))
    
    # Get only this salon's branches
    branches = Branch.query.filter_by(salon_id=salon.id).order_by(Branch.name.asc()).all()
    return render_template('admin/branches.html', branches=branches, salon=salon)

@admin_bp.route('/staff')
@login_required
@tenant_required
@subscription_required()
def manage_staff():
    """Manage staff for current salon only"""
    salon = get_current_salon()
    
    # Get only this salon's staff
    staff_members = Worker.query.filter_by(salon_id=salon.id, role='salonist').order_by(Worker.full_name).all()
    
    # Check subscription limits
    if len(staff_members) >= salon.max_staff:
        flash(f'You have reached your maximum staff limit ({salon.max_staff}). Upgrade your subscription to add more staff.', 'warning')
    
    return render_template('admin/manage_staff.html', staff_members=staff_members, salon=salon)

@admin_bp.route('/clients')
@login_required
@tenant_required
@subscription_required()
def manage_clients():
    """Manage clients for current salon only"""
    salon = get_current_salon()
    
    # Get only this salon's clients
    clients = Client.query.filter_by(salon_id=salon.id).order_by(Client.full_name).all()
    
    return render_template('admin/manage_clients.html', clients=clients, salon=salon)

# --- SALON MANAGEMENT ---
@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@tenant_required
def salon_settings():
    """Salon settings and subscription info"""
    salon = get_current_salon()
    
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
            
        elif action == 'update_shop_commission':
            commission_rate = request.form.get('shop_commission_rate', type=float)
            
            if commission_rate is not None and commission_rate >= 0 and commission_rate <= 100:
                salon.shop_commission_rate = commission_rate
                db.session.commit()
                flash(f"Shop commission rate updated to {commission_rate}%", "success")
            else:
                flash("Invalid commission rate. Please enter a value between 0 and 100.", "danger")
        
        return redirect(url_for('admin.salon_settings'))
    
    return render_template('admin/salon_settings.html', salon=salon)

@admin_bp.route('/upgrade')
@login_required
@tenant_required
def upgrade_subscription():
    """Upgrade subscription plan"""
    salon = get_current_salon()
    return render_template('admin/upgrade.html', salon=salon)
