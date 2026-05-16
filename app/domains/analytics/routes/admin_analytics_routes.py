"""Analytics routes: admin dashboard and service orders analysis (admin_bp)."""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import (Expense, Worker, Appointment, Product, ProductTransaction,
                        SupplierInvoice, Branch, ServiceOrder, db)
from sqlalchemy import func, or_
from datetime import datetime, timedelta
from app.decorators import roles_required
from app.middleware.access_control_middleware import billing_redirect
from app.admin import admin_bp


def get_managed_branches():
    try:
        existing = Branch.query.order_by(Branch.name.asc()).all()
        return [b.name for b in existing if b.is_active]
    except Exception:
        db.session.rollback()
        return []


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
