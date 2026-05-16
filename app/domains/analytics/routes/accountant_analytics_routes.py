"""Analytics routes: accountant dashboard (accountant_bp)."""
from flask import app, current_app, render_template, redirect, url_for, flash, request, session, jsonify
from app.models import Client, StaffDeduction, Product, ProductTransaction, Worker, Appointment, Service,SupplierInvoice ,RectificationLog,Expense,db,ServiceOrder,ServiceOrderItem
from app.decorators import roles_required
from flask_login import current_user, login_required
from datetime import datetime, timedelta
from sqlalchemy import func, inspect, Table, MetaData
from app.accountant import accountant_bp # Defined in accountant/__init__.py
 # Importing Service model for dynamic service loading
from sqlalchemy import or_, and_




import logging

from sqlalchemy.orm import joinedload

@accountant_bp.route('/dashboard')
@login_required
@roles_required('accountant')
def dashboard():
    branch = current_user.branch
    now = datetime.utcnow()
    
    # 1. Search and Recent Activity
    search_query = request.args.get('search_query', '').strip()
    
    # Use joinedload to force MySQL to connect to worker table to the appointments table
    query = Appointment.query.filter_by(branch=branch).options(joinedload(Appointment.worker))
    
    if search_query:
        # We explicitly join Worker here so we can search against the full_name column
        query = query.join(Worker, Appointment.worker_id == Worker.id).filter(or_(
            Appointment.receipt_no.ilike(f"%{search_query}%"),
            Worker.full_name.ilike(f"%{search_query}%"),
            Worker.username.ilike(f"%{search_query}%")
        ))
    
    recent_records = query.order_by(Appointment.appointment_time.desc()).limit(10).all()

    # Filter out appointments with missing workers to prevent errors
    recent_records = [r for r in recent_records if r.worker is not None]
    
    # 2. Daily Revenue Calculation (excluding model services)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_revenue = sum((r.total_cost or 0) for r in Appointment.query.filter(
        Appointment.branch == branch, 
        Appointment.appointment_time >= today_start,
        Appointment.is_model != True  # Exclude model services from revenue
    ).all())

    # 3. Individual Product Highlights using 'stock_quantity'
    low_stock_items = Product.query.filter(
        Product.branch == branch,
        or_(
            and_(Product.inventory_type == 'salon', Product.stock_quantity < 10),
            and_(Product.inventory_type == 'shop', Product.stock_quantity < 5)
        )
    ).all()

    return render_template('accountant/dashboard.html', 
                           recent_records=recent_records,
                           now=now,
                           today_revenue=today_revenue,
                           low_stock_items=low_stock_items,
                           search_query=search_query)
