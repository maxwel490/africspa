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


def get_week_start(date_value):
    days_to_subtract = (date_value.weekday() + 1) % 7
    return (date_value - timedelta(days=days_to_subtract)).replace(hour=0, minute=0, second=0, microsecond=0)


def get_fourth_sunday_week_start(date_value):
    month_start = datetime(date_value.year, date_value.month, 1)
    first_sunday_offset = (6 - month_start.weekday()) % 7
    fourth_sunday = month_start + timedelta(days=first_sunday_offset + 21)
    return get_week_start(fourth_sunday)


def normalize_specialty(specialty_value):
    value = (specialty_value or '').strip().lower()
    if 'cornrow' in value or 'conrow' in value:
        return 'Conrows'
    if 'braid' in value:
        return 'Braids'
    if 'undo' in value:
        return 'Undo'
    if 'nail' in value:
        return 'Nails'
    if 'wash' in value:
        return 'Wash'
    if 'makeup' in value:
        return 'Makeup'
    return 'Uncategorized'


# Tenant Payment Configuration System
def get_tenant_payment_options(tenant_id=None):
    """
    Get payment options configured for a specific tenant
    """
    if not tenant_id:
        tenant_id = current_user.salon_id
    
    # Default payment options if tenant doesn't have custom configuration
    default_options = [
        {'code': 'mpesa', 'name': 'M-Pesa', 'icon': 'fas fa-mobile-alt', 'is_default': True},
        {'code': 'bank', 'name': 'Bank', 'icon': 'fas fa-university', 'is_default': False},
        {'code': 'cash', 'name': 'Cash', 'icon': 'fas fa-money-bill', 'is_default': False},
        {'code': 'model', 'name': 'Model (No Payment)', 'icon': 'fas fa-user', 'is_default': False},
    ]
    
    # Try to get tenant-specific configuration from salon
    from app.models import Salon
    salon = Salon.query.filter_by(id=tenant_id).first()
    
    if salon and hasattr(salon, 'payment_config') and salon.payment_config:
        try:
            # Parse JSON configuration from salon
            import json
            custom_config = json.loads(salon.payment_config)
            
            # Merge with defaults, allowing tenant to override
            merged_options = []
            enabled_codes = [opt['code'] for opt in custom_config.get('enabled_methods', [])]
            
            for option in default_options:
                if option['code'] in enabled_codes:
                    # Find custom config for this method
                    custom_method = next((m for m in custom_config.get('enabled_methods', []) 
                                       if m['code'] == option['code']), None)
                    if custom_method:
                        merged_option = option.copy()
                        merged_option.update({
                            'name': custom_method.get('name', option['name']),
                            'icon': custom_method.get('icon', option['icon']),
                            'is_default': custom_method.get('is_default', option['is_default'])
                        })
                        merged_options.append(merged_option)
                    else:
                        merged_options.append(option)
            
            return merged_options if merged_options else default_options
        except (json.JSONDecodeError, AttributeError):
            pass
    
    return default_options

def save_tenant_payment_config(tenant_id, payment_config):
    """
    Save payment configuration for a tenant
    """
    from app.models import Salon
    import json
    
    salon = Salon.query.filter_by(id=tenant_id).first()
    if salon:
        salon.payment_config = json.dumps(payment_config)
        db.session.commit()
        return True
    return False


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

@accountant_bp.route('/record_work', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def record_work():
    """Redirect to service orders page filtered by paid status"""
    return redirect(url_for('accountant.service_orders') + '?status=paid')

@accountant_bp.route('/create-salonist', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def create_salonist():
    return redirect(url_for('accountant.manage_staff'))



@accountant_bp.route('/inventory', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def inventory():
    """Manages branch-specific stock levels with Department categorization."""
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        # 1. ISSUE STOCK (Deducting balance)
        if action == 'issue':
            product_id = request.form.get('product_id', type=int)
            worker_id = request.form.get('worker_id', type=int)
            selected_worker = None
            issue_type = (request.form.get('issue_type') or 'department').strip().lower()
            issue_department = (request.form.get('issue_department') or '').strip().title()
            qty_to_issue = request.form.get('quantity', type=int) or 0
            allowed_departments = {'Hair', 'Wash', 'Makeup', 'Nails'}
            allowed_issue_types = {'department', 'individual'}

            if not product_id or qty_to_issue <= 0:
                flash("Select product and enter a valid quantity.", "warning")
                return redirect(url_for('accountant.inventory'))

            if issue_department not in allowed_departments:
                flash("Select a valid issue department (Hair/Wash/Makeup/Nails).", "warning")
                return redirect(url_for('accountant.inventory'))

            if issue_type not in allowed_issue_types:
                flash("Select a valid issue type (Department or Individual Salonist).", "warning")
                return redirect(url_for('accountant.inventory'))

            if issue_type == 'individual':
                selected_worker = Worker.query.filter_by(id=worker_id, branch=current_user.branch, role='salonist').first()
                if not selected_worker:
                    flash("Select a valid salonist for individual issue.", "warning")
                    return redirect(url_for('accountant.inventory'))
            else:
                worker_id = None

            product = Product.query.get_or_404(product_id)

            if product.stock_quantity < qty_to_issue:
                flash(f"Insufficient stock for {product.name}!", "danger")
                return redirect(url_for('accountant.inventory'))

            try:
                product.stock_quantity -= qty_to_issue

                issue_txn = ProductTransaction(
                    transaction_no=f"ISS-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{product.id}"[:50],
                    product_id=product.id,
                    worker_id=worker_id,
                    quantity=qty_to_issue,
                    total_amount=float(product.unit_price or 0) * qty_to_issue,
                    department=issue_department,
                    transaction_type='Internal Use',
                    timestamp=datetime.utcnow()
                )
                db.session.add(issue_txn)

                issue_total = float(product.unit_price or 0) * qty_to_issue
                is_hair_department_issue = issue_type == 'department' and issue_department == 'Hair' and issue_total > 0
                is_individual_issue = issue_type == 'individual' and worker_id and issue_total > 0

                if is_individual_issue:
                    weekly_worker_deduction = StaffDeduction(
                        worker_id=worker_id,
                        branch=current_user.branch,
                        deduction_type='inventory_issue',
                        amount=issue_total,
                        product_name=f"{product.name} x{qty_to_issue}",
                        reason='Auto-generated from individual inventory issue',
                        week_start=get_week_start(datetime.utcnow())
                    )
                    db.session.add(weekly_worker_deduction)

                if is_hair_department_issue:
                    monthly_deduction = StaffDeduction(
                        worker_id=current_user.id,
                        deduction_type='global_mandatory',
                        amount=issue_total,
                        week_start=get_week_start(datetime.utcnow()),
                        product_name=f"Hair Department Issue: {product.name} x{qty_to_issue}",
                        reason='Auto-generated from inventory issue to Hair department',
                        target_role='Cornrows & Braids',
                        branch=current_user.branch
                    )
                    db.session.add(monthly_deduction)

                db.session.commit()

                if is_hair_department_issue:
                    flash(
                        f"Issued {qty_to_issue} {product.name} to Hair department. "
                        "Automatically added to Cornrows/Braids specialized deduction for the 4th week payout.",
                        "success"
                    )
                else:
                    if issue_type == 'individual':
                        worker_name = selected_worker.full_name if selected_worker and selected_worker.full_name else (selected_worker.username if selected_worker else 'selected salonist')
                        flash(
                            f"Issued {qty_to_issue} {product.name} to {worker_name} under {issue_department}. "
                            "The total amount has been added as this week's deduction.",
                            "success"
                        )
                    else:
                        flash(f"Issued {qty_to_issue} {product.name} to {issue_department}. Logged successfully.", "success")
            except Exception:
                db.session.rollback()
                flash("Could not process stock issue. Please try again.", "danger")
            return redirect(url_for('accountant.inventory'))

        # 2. ADD NEW PRODUCT
        elif not action:
            selling_price = float(request.form.get('price') or 0)
            inventory_type = request.form.get('inventory_type', 'salon')
            new_product = Product(
                name=request.form.get('name'),
                department=request.form.get('department'),
                category=request.form.get('category'),
                stock_quantity=int(request.form.get('quantity') or 0),
                unit_price=selling_price,
                buying_price=selling_price,
                branch=current_user.branch,
                inventory_type=inventory_type,
                salon_id=current_user.salon_id
            )
            db.session.add(new_product)
            db.session.commit()
            flash(f"Added {new_product.name} successfully!", "success")
            return redirect(url_for('accountant.inventory'))

    # --- GET REQUEST LOGIC ---
    # Check if salon has internal shop
    current_salon = current_user.salon
    has_internal_shop = current_salon.has_internal_shop if current_salon else False
    
    # Filter products based on inventory type and salon setup
    if has_internal_shop:
        # For salons with shop, show all inventory types but separate them
        products = Product.query.filter_by(branch=current_user.branch).all()
    else:
        # For salons without shop, only show salon inventory
        products = Product.query.filter_by(branch=current_user.branch, inventory_type='salon').all()
    
    # We fetch workers so they appear in your HTML dropdown (exclude superadmin)
    workers = Worker.query.filter_by(branch=current_user.branch).filter(Worker.role != 'superadmin').all()

    issued_logs = ProductTransaction.query \
        .join(Product, ProductTransaction.product_id == Product.id) \
        .options(joinedload(ProductTransaction.product_obj), joinedload(ProductTransaction.performed_by)) \
        .filter(
            Product.branch == current_user.branch,
            ProductTransaction.transaction_type == 'Internal Use'
        ) \
        .order_by(ProductTransaction.timestamp.desc()) \
        .limit(20) \
        .all()

    return render_template('accountant/inventory.html', 
                           products=products, 
                           workers=workers,
                           issued_logs=issued_logs,
                           has_internal_shop=has_internal_shop)


@accountant_bp.route('/inventory/edit/<int:product_id>', methods=['POST'])
@login_required
@roles_required('accountant')
def edit_product(product_id):
    """Handles updating product details including department and price."""
    product = Product.query.get_or_404(product_id)
    
    # Security check: Ensure accountant only edits their branch's stock
    if product.branch != current_user.branch:
        flash("Unauthorized access to this product.", "danger")
        return redirect(url_for('accountant.inventory'))

    product.name = request.form.get('name')
    product.department = request.form.get('department') # NEW
    product.category = request.form.get('category')
    product.unit_price = float(request.form.get('price') or 0)
    if not product.buying_price or product.buying_price <= 0:
        product.buying_price = product.unit_price
    
    db.session.commit()
    flash(f"Updated {product.name} successfully.", "info")
    return redirect(url_for('accountant.inventory'))


@accountant_bp.route('/inventory/delete/<int:product_id>', methods=['POST'])
@login_required
@roles_required('accountant')
def delete_product(product_id):
    """Safely removes a product or shows a custom error message."""
    product = Product.query.get_or_404(product_id)
    
    # Security: Ensure accountant only deletes from their own branch
    if product.branch == current_user.branch:
        try:
            db.session.delete(product)
            db.session.commit()
            flash(f"Successfully removed {product.name}.", "warning")
        except Exception:
            db.session.rollback()
            # This replaces the system error with your custom message
            flash("Sorry, ask admin for help.", "danger")
    
    return redirect(url_for('accountant.inventory'))

@accountant_bp.route('/commissions')
@login_required
@roles_required('accountant')
def weekly_commissions():
    """Calculates weekly payouts and ensures all UI variables are passed."""
    # Use provided date or default to current week
    date_str = request.args.get('start_date')
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
    else:
        target_date = datetime.utcnow()

    # Define the Sunday-Saturday window
    start_of_week = get_week_start(target_date)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)

    # Calculate navigation dates
    prev_week = (start_of_week - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week = (start_of_week + timedelta(days=7)).strftime('%Y-%m-%d')

    # Added joinedload to fetch worker details (full_name) efficiently for MySQL
    all_work = Appointment.query.options(joinedload(Appointment.worker)).filter(
        Appointment.branch == current_user.branch,
        Appointment.appointment_time >= start_of_week,
        Appointment.appointment_time <= end_of_week
    ).all()

    # Get all unique specialties from current salonists
    all_specialties = set()
    worker_profiles = {}
    gross_by_bucket = {}
    worker_bucket_keys = {}
    
    # Process work data to add actual commissions and build profiles
    for work in all_work:
        if not work.worker:
            continue

        worker_id = work.worker.id
        worker_name = work.worker.full_name if work.worker.full_name else work.worker.username
        worker_specialty = normalize_specialty(work.worker.specialty)

        # Create worker profile only if they have work
        if worker_id not in worker_profiles:
            worker_profiles[worker_id] = {
                'name': worker_name,
                'specialty': worker_specialty
            }

        # Add commission to the bucket
        bucket_key = (worker_id, worker_specialty)
        gross_by_bucket[bucket_key] = gross_by_bucket.get(bucket_key, 0.0) + (float(work.commission_earned) if work.commission_earned else 0.0)
        worker_bucket_keys.setdefault(worker_id, set()).add(bucket_key)
        
        # Add specialty from work data
        if work.worker.specialty:
            normalized = normalize_specialty(work.worker.specialty)
            if normalized:
                all_specialties.add(normalized)

    # Sort specialties alphabetically for consistent ordering
    specialty_order = sorted(list(all_specialties))
    
    # Worker-specific deductions (same-week deductions)
    weekly_deductions = StaffDeduction.query.options(joinedload(StaffDeduction.worker)).filter(
        StaffDeduction.branch == current_user.branch,
        StaffDeduction.week_start == start_of_week,
        StaffDeduction.deduction_type != 'global_mandatory'
    ).all()

    deductions_by_bucket = {}
    deduction_rows = []
    for deduction in weekly_deductions:
        if deduction.worker:
            worker_profiles[deduction.worker.id] = {
                'name': deduction.worker.full_name if deduction.worker.full_name else deduction.worker.username,
                'specialty': normalize_specialty(deduction.worker.specialty)
            }
            display_name = worker_profiles[deduction.worker.id]['name']
        else:
            display_name = f"Worker #{deduction.worker_id}"

        amount = float(deduction.amount or 0.0)
        worker_id = deduction.worker_id
        bucket_keys = list(worker_bucket_keys.get(worker_id, set()))

        if bucket_keys:
            gross_total = sum(gross_by_bucket.get(key, 0.0) for key in bucket_keys)
            if gross_total > 0:
                allocated_total = 0.0
                for idx, key in enumerate(bucket_keys):
                    if idx == len(bucket_keys) - 1:
                        allocation = amount - allocated_total
                    else:
                        ratio = gross_by_bucket.get(key, 0.0) / gross_total
                        allocation = round(amount * ratio, 2)
                        allocated_total += allocation
                    deductions_by_bucket[key] = deductions_by_bucket.get(key, 0.0) + allocation
            else:
                default_specialty = worker_profiles.get(worker_id, {}).get('specialty', 'Uncategorized')
                fallback_key = (worker_id, default_specialty)
                deductions_by_bucket[fallback_key] = deductions_by_bucket.get(fallback_key, 0.0) + amount
                worker_bucket_keys.setdefault(worker_id, set()).add(fallback_key)
        else:
            default_specialty = worker_profiles.get(worker_id, {}).get('specialty', 'Uncategorized')
            fallback_key = (worker_id, default_specialty)
            deductions_by_bucket[fallback_key] = deductions_by_bucket.get(fallback_key, 0.0) + amount
            worker_bucket_keys.setdefault(worker_id, set()).add(fallback_key)

        deduction_rows.append({
            'worker_name': display_name,
            'deduction_type': deduction.deduction_type,
            'amount': amount,
            'reason': deduction.reason or ''
        })

    # Mandatory deduction: applied on the 4th week of the same month as the deduction entry
    specialists = Worker.query.filter(
        Worker.branch == current_user.branch,
        Worker.role == 'salonist'
    ).all()

    specialist_ids = [w.id for w in specialists]
    
    # Handle new salons with no salonists
    if not specialists:
        return render_template('accountant/commissions.html', 
                           grouped_summary={},
                           specialty_order=[],
                           specialty_totals={},
                           payout_rows=[],
                           total_payout=0.0,
                           total_gross=0.0,
                           total_deductions=0.0,
                           deduction_rows=[],
                           start_of_week=start_of_week,
                           end_of_week=end_of_week,
                           prev_week=prev_week,
                           next_week=next_week,
                           branch=current_user.branch,
                           no_salonists=True)
    for worker in specialists:
        worker_profiles[worker.id] = {
            'name': worker.full_name if worker.full_name else worker.username,
            'specialty': normalize_specialty(worker.specialty)
        }
    
    # Get tenant-configurable backbar groups for mandatory deductions
    from app.models import BackbarGroup
    backbar_groups = BackbarGroup.query.filter_by(salon_id=current_user.salon_id, is_active=True).all()
    
    due_mandatory = []
    # Collect mandatory deductions for all active backbar groups
    for group in backbar_groups:
        group_deductions = StaffDeduction.query.filter_by(
            branch=current_user.branch,
            target_role=group.name,
            deduction_type='global_mandatory'
        ).all()
        for entry in group_deductions:
            due_week = get_fourth_sunday_week_start(entry.created_at or datetime.utcnow())
            if due_week == start_of_week:
                due_mandatory.append(entry)
    
    # Also handle accountant shop deductions if shop is enabled
    current_salon = current_user.salon
    if current_salon and current_salon.has_internal_shop:
        accountant_deductions = StaffDeduction.query.filter_by(
            branch=current_user.branch,
            target_role='Accountant',
            deduction_type='global_mandatory'
        ).all()
        for entry in accountant_deductions:
            due_week = get_fourth_sunday_week_start(entry.created_at or datetime.utcnow())
            if due_week == start_of_week:
                due_mandatory.append(entry)

    mandatory_total = sum(float(d.amount or 0.0) for d in due_mandatory)
    mandatory_per_worker = (mandatory_total / len(specialist_ids)) if specialist_ids else 0.0

    if mandatory_per_worker > 0:
        for specialist_id in specialist_ids:
            bucket_keys = list(worker_bucket_keys.get(specialist_id, set()))
            if bucket_keys:
                gross_total = sum(gross_by_bucket.get(key, 0.0) for key in bucket_keys)
                if gross_total > 0:
                    allocated_total = 0.0
                    for idx, key in enumerate(bucket_keys):
                        if idx == len(bucket_keys) - 1:
                            allocation = mandatory_per_worker - allocated_total
                        else:
                            ratio = gross_by_bucket.get(key, 0.0) / gross_total
                            allocation = round(mandatory_per_worker * ratio, 2)
                            allocated_total += allocation
                        deductions_by_bucket[key] = deductions_by_bucket.get(key, 0.0) + allocation
                else:
                    fallback_specialty = worker_profiles.get(specialist_id, {}).get('specialty', 'Uncategorized')
                    fallback_key = (specialist_id, fallback_specialty)
                    deductions_by_bucket[fallback_key] = deductions_by_bucket.get(fallback_key, 0.0) + mandatory_per_worker
                    worker_bucket_keys.setdefault(specialist_id, set()).add(fallback_key)
            else:
                fallback_specialty = worker_profiles.get(specialist_id, {}).get('specialty', 'Uncategorized')
                fallback_key = (specialist_id, fallback_specialty)
                deductions_by_bucket[fallback_key] = deductions_by_bucket.get(fallback_key, 0.0) + mandatory_per_worker
                worker_bucket_keys.setdefault(specialist_id, set()).add(fallback_key)

    if mandatory_total > 0:
        for specialist_id in specialist_ids:
            specialist_name = worker_profiles.get(specialist_id, {}).get('name', f'Worker #{specialist_id}')
            deduction_rows.append({
                'worker_name': specialist_name,
                'deduction_type': 'mandatory_specialty_4th_week_monthly',
                'amount': mandatory_per_worker,
                'reason': 'Shared mandatory back-bar deduction in 4th week of month'
            })

    payout_rows = []
    all_bucket_keys = set(list(gross_by_bucket.keys()) + list(deductions_by_bucket.keys()))
    for worker_id, specialty in all_bucket_keys:
        profile = worker_profiles.get(worker_id, {})
        worker_name = profile.get('name', f'Worker #{worker_id}')
        gross = float(gross_by_bucket.get((worker_id, specialty), 0.0))
        deduction_value = float(deductions_by_bucket.get((worker_id, specialty), 0.0))
        net = max(0.0, gross - deduction_value)
        payout_rows.append({
            'worker_name': worker_name,
            'specialty': specialty,
            'gross': gross,
            'deduction': deduction_value,
            'net': net
        })

    grouped_summary = {key: [] for key in specialty_order}
    for row in payout_rows:
        if row['specialty'] in grouped_summary:
            grouped_summary[row['specialty']].append(row)

    specialty_totals = {}
    for specialty in specialty_order:
        rows = grouped_summary.get(specialty, [])
        specialty_totals[specialty] = {
            'count': len(rows),
            'gross': sum((item['gross'] or 0.0) for item in rows),
            'deduction': sum((item['deduction'] or 0.0) for item in rows),
            'net': sum((item['net'] or 0.0) for item in rows)
        }

    total_payout = sum((row['net'] or 0.0) for row in payout_rows)

    return render_template('accountant/commissions.html', 
                           grouped_summary=grouped_summary,
                           specialty_order=specialty_order,
                           specialty_totals=specialty_totals,
                           payout_rows=payout_rows,
                           total_payout=total_payout,
                           total_gross=sum((row['gross'] or 0.0) for row in payout_rows),
                           total_deductions=sum((row['deduction'] or 0.0) for row in payout_rows),
                           deduction_rows=deduction_rows,
                           start_of_week=start_of_week,
                           end_of_week=end_of_week,
                           prev_week=prev_week,
                           next_week=next_week,
                           branch=current_user.branch)


@accountant_bp.route('/manage-staff', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def manage_staff():
    if request.method == 'POST':
# DEBUG:         print("=== DEBUG: Form submission received ===")
# DEBUG:         print("Form data:", dict(request.form))
        
        full_name = (request.form.get('full_name') or '').strip()
        username = (request.form.get('username') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        email = (request.form.get('email') or '').strip()
        id_number = (request.form.get('id_number') or '').strip()
        password = (request.form.get('password') or '').strip()
        selected_specialty = (request.form.get('specialty') or '').strip()

# DEBUG:         print(f"Processed values:")
# DEBUG:         print(f"  full_name: '{full_name}'")
# DEBUG:         print(f"  username: '{username}'")
# DEBUG:         print(f"  phone: '{phone}'")
# DEBUG:         print(f"  id_number: '{id_number}'")
# DEBUG:         print(f"  password: '{password}'")
# DEBUG:         print(f"  selected_specialty: '{selected_specialty}'")

        if not all([full_name, username, phone, id_number, password, selected_specialty]):
# DEBUG:             print("=== VALIDATION FAILED: Missing required fields ===")
            flash("All required fields must be filled.", "danger")
            return redirect(url_for('accountant.manage_staff'))

        if not selected_specialty:
            flash("Specialty is required.", "danger")
            return redirect(url_for('accountant.manage_staff'))

        existing_errors = []
        username_suggestions = []
        
        # Check username conflicts
        existing_user = Worker.query.filter_by(username=username).first()
        if existing_user:
            existing_errors.append(f"Username '{username}' already exists")
            # Generate unique username suggestions based on branch and name
            base_suggestions = [
                f"{username}_{current_user.branch.lower()}",
                f"{username}_{current_user.branch.lower()[:3]}",
                f"{username}_{full_name.split()[0].lower() if full_name else 'salon'}",
                f"{username}_{current_user.salon_id or 'salon'}",
                f"{username}_{datetime.utcnow().strftime('%Y')}",
            ]
            
            # Filter out taken suggestions and limit to 3
            for suggestion in base_suggestions[:5]:
                if not Worker.query.filter_by(username=suggestion).first():
                    username_suggestions.append(suggestion)
                    if len(username_suggestions) >= 3:
                        break
            
            if username_suggestions:
                flash(f"Username '{username}' already exists. Try: {', '.join(username_suggestions)}", "warning")
            else:
                flash(f"Username '{username}' already exists. Please choose a different username.", "danger")
                return redirect(url_for('accountant.manage_staff'))
        
        # Check ID conflicts
        if Worker.query.filter_by(id_number=id_number).first():
            existing_errors.append("ID Number already registered")
        
        # Check email conflicts
        if email and Worker.query.filter_by(email=email).first():
            existing_errors.append("Email already registered")

        if existing_errors and not username_suggestions:  # Only redirect if we don't have username suggestions
            flash("Error: " + ", ".join(existing_errors), "danger")
            return redirect(url_for('accountant.manage_staff'))

        try:
            if len(password) < 6:
                raise ValueError("Password must be at least 6 characters long.")
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for('accountant.manage_staff'))

        # Create new salonist with proper error handling
        new_worker = Worker(
            full_name=full_name,
            username=username,
            phone=phone,
            email=email,
            id_number=id_number,
            specialty=selected_specialty,
            role='salonist',
            branch=current_user.branch,
            salon_id=current_user.salon_id,
            created_by_id=current_user.id
        )

        try:
            new_worker.set_password(password)
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for('accountant.manage_staff'))

        try:
            db.session.add(new_worker)
            db.session.commit()
            flash(f"Salonist {new_worker.full_name} (@{new_worker.username}) registered successfully!", "success")
            return redirect(url_for('accountant.manage_staff'))
        except Exception as e:
            db.session.rollback()
            flash("Error creating staff member. Please try again.", "danger")

    staff_members = Worker.query.filter_by(role='salonist', branch=current_user.branch).all()
    
    all_specialties = Worker.query.filter_by(branch=current_user.branch).with_entities(Worker.specialty).distinct().all()
    specialties = [specialty[0] for specialty in all_specialties if specialty[0]]
    specialties.sort()  
    
    now_value = datetime.utcnow()
    staff_status = {}
    for staff in staff_members:
        last_work_at = staff.get_last_recorded_work_time()
        is_inactive = staff.is_inactive_for_no_work(days_without_work=14, reference_time=now_value)
        staff_status[staff.id] = {
            'last_work_at': last_work_at,
            'is_inactive': is_inactive
        }

    # Determine phone formatting based on branch location
    branch_lower = current_user.branch.lower()
    phone_config = {
        'placeholder': '719857198 or +254719857198',
        'help_text': 'Enter local number (e.g., 719857198) or full international format'
    }
    
    # Kenya branches
    if any(kenya_branch in branch_lower for kenya_branch in ['nairobi', 'mombasa', 'kisumu', 'nakuru', 'eldoret', 'kenya']):
        phone_config = {
            'placeholder': '719857198',
            'help_text': 'Enter Kenyan number without country code (e.g., 719857198)'
        }
    # South Africa branches  
    elif any(sa_branch in branch_lower for sa_branch in ['johannesburg', 'cape town', 'durban', 'pretoria', 'bloemfontein', 'south africa']):
        phone_config = {
            'placeholder': '821234567',
            'help_text': 'Enter South African number without country code (e.g., 821234567)'
        }
    # Nigeria branches
    elif any(ng_branch in branch_lower for ng_branch in ['lagos', 'abuja', 'port harcourt', 'kano', 'ibadan', 'nigeria']):
        phone_config = {
            'placeholder': '8012345678',
            'help_text': 'Enter Nigerian number without country code (e.g., 8012345678)'
        }
    # Ghana branches
    elif any(gh_branch in branch_lower for gh_branch in ['accra', 'kumasi', 'tamale', 'ghana']):
        phone_config = {
            'placeholder': '201234567',
            'help_text': 'Enter Ghanaian number without country code (e.g., 201234567)'
        }
    # Uganda branches
    elif any(ug_branch in branch_lower for ug_branch in ['kampala', 'entebbe', 'jinja', 'uganda']):
        phone_config = {
            'placeholder': '712345678',
            'help_text': 'Enter Ugandan number without country code (e.g., 712345678)'
        }
    # Tanzania branches
    elif any(tz_branch in branch_lower for tz_branch in ['dar es salaam', 'arusha', 'mwanza', 'tanzania']):
        phone_config = {
            'placeholder': '712345678',
            'help_text': 'Enter Tanzanian number without country code (e.g., 712345678)'
        }

    return render_template('accountant/manage_staff.html', 
                          staff_members=staff_members, 
                          staff_status=staff_status, 
                          specialties=specialties,
                          phone_placeholder=phone_config['placeholder'],
                          phone_help_text=phone_config['help_text'])


@accountant_bp.route('/check-username')
@login_required
@roles_required('accountant')
def check_username():
    """API endpoint to check username availability in real-time"""
    username = request.args.get('username', '').strip()
    
    if not username or len(username) < 3:
        return jsonify({'available': False, 'message': 'Username must be at least 3 characters'})
    
    existing_user = Worker.query.filter_by(username=username).first()
    if existing_user:
        # Generate suggestions similar to the main form
        suggestions = []
        base_suggestions = [
            f"{username}_{current_user.branch.lower()}",
            f"{username}_{current_user.branch.lower()[:3]}",
            f"{username}_{datetime.utcnow().strftime('%Y')}",
        ]
        
        for suggestion in base_suggestions[:5]:
            if not Worker.query.filter_by(username=suggestion).first():
                suggestions.append(suggestion)
                if len(suggestions) >= 3:
                    break
        
        return jsonify({
            'available': False, 
            'message': f'Username "{username}" is already taken',
            'suggestions': suggestions
        })
    else:
        return jsonify({'available': True, 'message': 'Username is available'})


@accountant_bp.route('/edit-staff/<int:staff_id>', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def edit_staff(staff_id):
    staff = Worker.query.get_or_404(staff_id)
    if request.method == 'POST':
        # Updating basic credentials and specialty
        staff.username = request.form.get('username')
        staff.specialty = request.form.get('specialty')
        
        # Updating the new detailed fields
        staff.full_name = request.form.get('full_name')
        staff.phone = request.form.get('phone')
        staff.email = request.form.get('email')
        staff.id_number = request.form.get('id_number')

        # Preserve username if not provided in form
        username = request.form.get('username')
        if username:
            staff.username = username
        elif not staff.username:
            flash("Username cannot be empty.", "danger")
            return redirect(url_for('accountant.edit_staff', staff_id=staff.id))

        # Updating financial data
        staff.base_salary = float(request.form.get('base_salary', 0))

        db.session.commit()
        flash("Staff profile updated successfully!", "success")
        return redirect(url_for('accountant.manage_staff'))

    return render_template('accountant/edit_staff.html', staff=staff)

@accountant_bp.route('/reset-password/<int:staff_id>', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def reset_password(staff_id):
    staff = Worker.query.get_or_404(staff_id)
    if request.method == 'POST':
        new_password = request.form.get('password')
        # Preserve username if not present
        if not staff.username:
            flash("Username cannot be empty.", "danger")
            return redirect(url_for('accountant.reset_password', staff_id=staff.id))
        staff.set_password(new_password)  # Uses the helper in Worker model
        db.session.commit()
        flash(f"Password for {staff.username} has been updated.", "success")
        return redirect(url_for('accountant.manage_staff'))
    return render_template('accountant/reset_password.html', staff=staff)


@accountant_bp.route('/delete-staff/<int:staff_id>')
@login_required
@roles_required('accountant')
def delete_staff(staff_id):
    staff = Worker.query.get_or_404(staff_id)
    # Check if they have appointments before deleting to avoid database errors
    if staff.appointments:
        flash("Cannot delete staff with existing appointment records. Consider deactivating them instead.", "danger")
    else:
        db.session.delete(staff)
        db.session.commit()
        flash("Staff member deleted.", "info")
    return redirect(url_for('accountant.manage_staff'))


@accountant_bp.route('/add-client', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def add_client():  # This name MUST match 'add_client' used in url_for
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        # Clients are global - not tied to specific branch
        branch = current_user.branch  # Still track which branch registered them

        try:
            new_client = Client(
                full_name=full_name,
                phone=phone,
                branch=branch  # Track registration branch, but client can visit any branch
            )
            db.session.add(new_client)
            db.session.commit()
            flash(f"Client {full_name} registered successfully! (Global client - can visit any branch)", "success")
            return redirect(url_for('accountant.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash("Error: Phone number might already be registered.", "danger")

    return render_template('accountant/add_client.html')


@accountant_bp.route('/back-bar', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def back_bar_management():
    """Tenant-configurable backbar deductions management"""
    from app.models import Salon, BackbarGroup
    
    branch = current_user.branch
    
    # Get current salon configuration
    current_salon = Salon.query.filter_by(id=current_user.salon_id).first() if current_user.salon_id else None
    has_internal_shop = current_salon.has_internal_shop if current_salon else False
    has_backbar_enabled = getattr(current_salon, 'has_backbar', True)  # Default to True for backward compatibility
    
    # Shop is run by accountant, not shop staff - no shop workers exist
    shop_workers = []  # No dedicated shop staff
    
    # Check if backbar deductions are enabled for this salon
    if not has_backbar_enabled:
        flash('Backbar deductions are not enabled for this salon.', 'info')
        return redirect(url_for('accountant.dashboard'))
    
    # Handle form submissions
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_mandatory':
            inventory_type = request.form.get('inventory_type', 'salon')
            backbar_group_id = request.form.get('backbar_group_id', type=int)
            product_name = request.form.get('product_name', '').strip()
            total_amount = float(request.form.get('total_amount', 0))
            
            # Validate required fields
            if not product_name:
                flash('Product name is required.', 'danger')
                return redirect(url_for('accountant.back_bar_management'))
            
            if total_amount <= 0:
                flash('Amount must be greater than 0.', 'danger')
                return redirect(url_for('accountant.back_bar_management'))
            
            # Handle shop inventory deductions
            if inventory_type == 'shop':
                # Shop is run by accountant, assign to accountant group
                backbar_group_id = None
                target_role = 'Accountant'  # Shop deductions assigned to accountant
            else:
                # For salon inventory, require a valid backbar group
                if not backbar_group_id:
                    flash('Please select a target group for this deduction.', 'danger')
                    return redirect(url_for('accountant.back_bar_management'))
                
                # Validate the backbar group belongs to this salon
                group = BackbarGroup.query.filter_by(id=backbar_group_id, salon_id=current_user.salon_id, is_active=True).first()
                if not group:
                    flash('Invalid target group selected.', 'danger')
                    return redirect(url_for('accountant.back_bar_management'))
                
                target_role = group.name
            
            # Create the mandatory deduction
            new_deduction = StaffDeduction(
                worker_id=current_user.id,
                deduction_type='global_mandatory',
                amount=total_amount,
                week_start=get_week_start(datetime.utcnow()),
                product_name=product_name,
                target_role=target_role,
                branch=branch,
                inventory_type=inventory_type,
                backbar_group_id=backbar_group_id,
                created_by_id=current_user.id
            )
            
            try:
                db.session.add(new_deduction)
                db.session.commit()
                
                inventory_name = 'Shop' if inventory_type == 'shop' else 'Salon'
                flash(f'Mandatory {inventory_name} deduction saved. It will apply after 4 weeks.', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error saving deduction. Please try again.', 'danger')

        elif action == 'add_worker_deduction':
            worker_id = request.form.get('worker_id', type=int)
            deduction_type = request.form.get('deduction_type')
            amount = float(request.form.get('amount', 0))
            reason = request.form.get('reason', '').strip()
            inventory_type = request.form.get('inventory_type', 'salon')

            # Validate worker
            worker = Worker.query.filter_by(id=worker_id, branch=branch, role='salonist').first()
            if not worker:
                flash('Invalid salonist selected.', 'danger')
                return redirect(url_for('accountant.back_bar_management'))

            # Validate amount
            if amount <= 0:
                flash('Amount must be greater than 0.', 'danger')
                return redirect(url_for('accountant.back_bar_management'))

            # Validate inventory type and deduction type combinations
            if inventory_type == 'shop' and not has_internal_shop:
                flash('Shop inventory is not enabled for this salon.', 'danger')
                return redirect(url_for('accountant.back_bar_management'))

            valid_deduction_types = ['inventory_damage', 'staff_purchase', 'inventory_issue']
            if inventory_type == 'shop':
                valid_deduction_types.extend(['shop_damage', 'shop_purchase'])
            
            if deduction_type not in valid_deduction_types:
                flash('Invalid deduction type.', 'danger')
                return redirect(url_for('accountant.back_bar_management'))

            # Create the worker deduction
            week_start = get_week_start(datetime.utcnow())
            new_staff_deduction = StaffDeduction(
                worker_id=worker.id,
                branch=branch,
                deduction_type=deduction_type,
                amount=amount,
                reason=reason,
                week_start=week_start,
                inventory_type=inventory_type,
                created_by_id=current_user.id
            )
            
            try:
                db.session.add(new_staff_deduction)
                db.session.commit()
                flash('Worker deduction saved and will be deducted in this week commission.', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error saving worker deduction. Please try again.', 'danger')

        return redirect(url_for('accountant.back_bar_management'))

    # GET request - build the page data
    
    # Get all salonists for worker deduction form
    all_salonists = Worker.query.filter_by(branch=branch, role='salonist').order_by(Worker.full_name).all()
    
    # Get active backbar groups for this salon
    backbar_groups = BackbarGroup.query.filter_by(salon_id=current_user.salon_id, is_active=True).all()
    
    # Build target groups from tenant-defined groups
    target_groups = []
    for group in backbar_groups:
        eligible_workers = group.get_eligible_workers(branch)
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
    
    # Add accountant shop group if internal shop is enabled
    if has_internal_shop:
        accountant_shop_group = {
            'id': None,  # No BackbarGroup for accountant shop
            'name': 'Accountant',
            'description': 'Shop run by accountant',
            'specialties': [],
            'employment_types': ['accountant'],
            'workers': [current_user],  # Accountant as the shop worker
            'icon': 'bi-person-badge',
            'color': 'info'
        }
        target_groups.append(accountant_shop_group)
    
    # If no target groups exist, show a helpful message
    if not target_groups:
        flash('No backbar groups configured. Please contact your administrator to set up backbar groups.', 'warning')
        return render_template('accountant/back_bar.html', 
                               target_groups=[],
                               group_deductions={},
                               group_totals={},
                               group_per_person={},
                               staff_deductions=[],
                               all_salonists=all_salonists,
                               has_internal_shop=has_internal_shop)
    
    # Fetch deductions for each target group (last 30 days)
    last_30_days = datetime.utcnow() - timedelta(days=30)
    group_deductions = {}
    
    for group in target_groups:
        if group['name'] == 'Accountant':
            # Shop deductions (run by accountant)
            deductions = StaffDeduction.query.filter(
                StaffDeduction.branch == branch,
                StaffDeduction.created_at >= last_30_days,
                StaffDeduction.target_role == group['name'],
                StaffDeduction.deduction_type == 'global_mandatory',
                StaffDeduction.inventory_type == 'shop'
            ).all()
        else:
            # Salon deductions for this group
            deductions = StaffDeduction.query.filter(
                StaffDeduction.branch == branch,
                StaffDeduction.created_at >= last_30_days,
                StaffDeduction.target_role == group['name'],
                StaffDeduction.deduction_type == 'global_mandatory',
                (StaffDeduction.inventory_type == 'salon') | (StaffDeduction.inventory_type.is_(None))
            ).all()
        
        group_deductions[group['name']] = deductions

    # Get current week worker deductions
    current_week_start = get_week_start(datetime.utcnow())
    weekly_deduction_types = ['inventory_damage', 'staff_purchase', 'inventory_issue']
    if has_internal_shop:
        weekly_deduction_types.extend(['shop_damage', 'shop_purchase'])
    
    staff_deductions = StaffDeduction.query.options(joinedload(StaffDeduction.worker)).filter(
        StaffDeduction.branch == branch,
        StaffDeduction.week_start == current_week_start,
        StaffDeduction.deduction_type.in_(weekly_deduction_types)
    ).order_by(StaffDeduction.created_at.desc()).all()
    
    # Calculate totals and per-person amounts for each group
    group_totals = {}
    group_per_person = {}
    
    for group in target_groups:
        group_name = group['name']
        deductions = group_deductions.get(group_name, [])
        total_cost = sum((d.amount or 0) for d in deductions)
        num_workers = len(group['workers'])
        per_person = total_cost / num_workers if num_workers > 0 else 0.0
        
        group_totals[group_name] = total_cost
        group_per_person[group_name] = per_person

    return render_template('accountant/back_bar.html', 
                           target_groups=target_groups,
                           group_deductions=group_deductions,
                           group_totals=group_totals,
                           group_per_person=group_per_person,
                           staff_deductions=staff_deductions,
                           all_salonists=all_salonists,
                           has_internal_shop=has_internal_shop)


@accountant_bp.route('/settlements', methods=['GET', 'POST'])
@login_required
@roles_required('accountant', 'admin')
def settlements():
    user_branch_full = (current_user.branch or '').strip()
    short_code = user_branch_full.split()[0] if user_branch_full else 'GEN'

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_invoice':
            try:
                invoice_date_str = request.form.get('invoice_date')
                # Parse date or default to now
                date_received = datetime.strptime(invoice_date_str, '%Y-%m-%d') if invoice_date_str else datetime.utcnow()

                # 1. Record the Invoice
                new_inv = SupplierInvoice(
                    supplier_name=request.form.get('supplier'),
                    invoice_number=request.form.get('inv_no'),
                    amount=0.0,
                    branch=user_branch_full,
                    status='Pending',
                    date_received=date_received
                )
                db.session.add(new_inv)
                db.session.flush() # Secure the ID for the foreign keys below

                # 2. Process Items
                p_ids = request.form.getlist('product_id[]')
                p_qtys = request.form.getlist('product_qty[]')
                p_unit_prices = request.form.getlist('product_unit_price[]')
                p_new_names = request.form.getlist('new_product_name[]')
                invoice_vat_rate = float(request.form.get('invoice_vat') or 0.0)
                if invoice_vat_rate < 0:
                    raise ValueError("Invoice VAT cannot be negative.")
                vat_factor = 1 + (invoice_vat_rate / 100.0)

                grand_total = 0.0
                item_lines = []

                for idx, (p_id, p_qty, p_unit_price, p_new_name) in enumerate(zip(p_ids, p_qtys, p_unit_prices, p_new_names), start=1):
                    if p_id and p_qty:
                        qty = int(p_qty)
                        new_name = (p_new_name or '').strip()
                        product = None

                        if p_id == '__new__':
                            if not new_name:
                                raise ValueError(f"Row {idx}: Enter a name for the new item.")
                            product = Product.query.filter(
                                Product.branch == user_branch_full,
                                func.lower(Product.name) == new_name.lower()
                            ).first()
                            if not product:
                                # Default to salon inventory type for new products created via settlements
                                inventory_type = 'salon'
                                product = Product(
                                    name=new_name,
                                    stock_quantity=0,
                                    unit_price=0.0,
                                    buying_price=0.0,
                                    branch=user_branch_full,
                                    inventory_type=inventory_type,
                                    salon_id=current_user.salon_id,
                                    reorder_level=5
                                )
                                db.session.add(product)
                                db.session.flush()
                        else:
                            product = db.session.get(Product, int(p_id))

                        unit_price_ex_vat = float(p_unit_price or 0.0)
                        
                        if product and qty > 0 and unit_price_ex_vat >= 0:
                            # Update Stock
                            product.stock_quantity += qty
                            previous_buying_price = float(product.buying_price or 0.0)
                            unit_price_incl_vat = unit_price_ex_vat * vat_factor
                            product.buying_price = unit_price_incl_vat

                            line_subtotal = unit_price_ex_vat * qty
                            tax_amount = line_subtotal * (invoice_vat_rate / 100.0)
                            line_total = line_subtotal + tax_amount
                            grand_total += line_total

                            item_lines.append(
                                f"{product.name}: qty={qty}, buy_prev={previous_buying_price:.2f}, buy_ex_vat={unit_price_ex_vat:.2f}, vat={invoice_vat_rate:.2f}%, buy_incl_vat={unit_price_incl_vat:.2f}, total={line_total:.2f}"
                            )
                            
                            # Create Log Entry
                            t_no = f"RST-{short_code}-{new_inv.invoice_number}-{product.id}-{idx}"[:50]
                            txn = ProductTransaction(
                                transaction_no=t_no,
                                product_id=product.id,
                                invoice_id=new_inv.id,
                                department=product.department, # MATCHES YOUR MODEL 'department'
                                worker_id=current_user.id,
                                quantity=qty,
                                total_amount=line_total,
                                transaction_type='Restock',
                                timestamp=datetime.utcnow()
                            )
                            db.session.add(txn)

                            if abs(previous_buying_price - unit_price_incl_vat) > 0.0001:
                                price_txn_no = f"PRC-{short_code}-{new_inv.invoice_number}-{product.id}-{idx}"[:50]
                                price_txn = ProductTransaction(
                                    transaction_no=price_txn_no,
                                    product_id=product.id,
                                    invoice_id=new_inv.id,
                                    department=product.department,
                                    worker_id=current_user.id,
                                    quantity=0,
                                    total_amount=unit_price_incl_vat,
                                    transaction_type='Price Update',
                                    timestamp=datetime.utcnow()
                                )
                                db.session.add(price_txn)

                new_inv.amount = grand_total
                new_inv.items_summary = ' | '.join(item_lines)

                db.session.commit()
                flash("Invoice recorded and stock updated successfully.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error recording invoice: {str(e)}", "danger")

        elif action == 'settle_single':
            inv_id = request.form.get('invoice_id', type=int)
            target = SupplierInvoice.query.filter_by(id=inv_id, branch=user_branch_full).first()
            if target:
                target.status = 'Paid'
                db.session.commit()
                flash(f"Invoice {target.invoice_number} settled.", "success")

        elif action == 'settle_bulk':
            unpaid = SupplierInvoice.query.filter_by(branch=user_branch_full, status='Pending').all()
            for inv in unpaid:
                inv.status = 'Paid'
            db.session.commit()
            flash(f"Bulk settlement complete for {len(unpaid)} invoices.", "success")

        return redirect(url_for('accountant.settlements'))

    # GET DATA
    products_list = Product.query.filter(
        or_(
            Product.branch == user_branch_full,
            Product.branch.ilike(f"{short_code}%")
        )
    ).order_by(Product.name).all()
    invoices = SupplierInvoice.query.filter_by(branch=user_branch_full, status='Pending').order_by(SupplierInvoice.date_received.desc()).all()
    supplier_names = [
        row[0] for row in db.session.query(SupplierInvoice.supplier_name)
        .filter(SupplierInvoice.branch == user_branch_full)
        .distinct()
        .order_by(SupplierInvoice.supplier_name.asc())
        .all()
        if row[0]
    ]
    total_pending = sum(inv.amount for inv in invoices)

    return render_template('accountant/settlement.html', 
                           invoices=invoices, 
                           products=products_list, 
                           supplier_names=supplier_names,
                           total_pending=total_pending,
                           now=datetime.utcnow())


@accountant_bp.route('/shop')
@login_required
@roles_required('accountant')
def shop():
    """Displays items and recent shop transactions."""
    shop_products = Product.query.filter(
        Product.branch == current_user.branch,
        Product.inventory_type == 'shop'
    ).all()

    # NEW: Fetch the 10 most recent direct sales to show on the page
    recent_sales = ProductTransaction.query.filter_by(transaction_type='Direct')\
        .order_by(ProductTransaction.timestamp.desc()).limit(10).all()
    
    return render_template('accountant/shop.html', 
                           shop_products=shop_products, 
                           recent_sales=recent_sales)


@accountant_bp.route('/shop/process-sale', methods=['POST'])
@login_required
@roles_required('accountant')
def process_direct_sale():
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', type=int) or 0
    # NEW: Capture the manual transaction number from the form
    txn_no = request.form.get('transaction_no')

    if not product_id or quantity <= 0 or not txn_no:
        flash("Invalid sale request. Ensure all fields including Transaction Number are filled.", "warning")
        return redirect(url_for('accountant.shop'))

    product = Product.query.get_or_404(product_id)

    if product.stock_quantity < quantity:
        flash(f"Insufficient stock for {product.name}.", "danger")
        return redirect(url_for('accountant.shop'))

    try:
        total_price = float(product.unit_price or 0) * quantity
        
        product.stock_quantity -= quantity

        new_transaction = ProductTransaction(
            transaction_no=txn_no, # Use the accountant's input
            product_id=product.id,
            quantity=quantity,
            total_amount=total_price,
            transaction_type='Direct',
            appointment_id=None
        )
        
        db.session.add(new_transaction)
        db.session.commit()

        flash(f"Sale {txn_no} recorded successfully.", "success")
    except Exception as e:
        db.session.rollback()
        # Handle duplicate transaction numbers gracefully
        if 'UNIQUE constraint' in str(e):
            flash("Error: This Transaction Number has already been used.", "danger")
        else:
            flash(f"Could not process sale: {str(e)}", "danger")

    return redirect(url_for('accountant.shop'))
    



@accountant_bp.route('/service-rectification', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def service_rectification():
    # Check if tenant has service rectification enabled
    if not current_user.salon.enable_service_rectification:
        flash("Service rectification is not enabled for your salon.", "info")
        return redirect(url_for('accountant.dashboard'))
    
    branch = current_user.branch

    def normalize_rectification_service(service_value, department_value=None):
        value = (service_value or '').strip().lower()
        # Enhanced service normalization with better categorization
        service_patterns = {
            'undo': 'Undo',
            'cornrow': 'Hair',
            'conrow': 'Hair', 
            'braid': 'Hair',
            'hair': 'Hair',
            'wash': 'Wash',
            'makeup': 'Makeup',
            'make up': 'Makeup',
            'nail': 'Nails'
        }
        
        for pattern, category in service_patterns.items():
            if pattern in value:
                return category

        # Fallback to department classification
        dept_value = (department_value or '').strip().lower()
        dept_mapping = {
            'hair': 'Hair',
            'wash': 'Wash', 
            'makeup': 'Makeup',
            'nails': 'Nails'
        }
        
        return dept_mapping.get(dept_value, (service_value or '').strip().title())

    def compute_redo_amount(service_rows):
        if not service_rows:
            return 0.0

        primary_row = next(
            (row for row in service_rows if 'assistant' not in (row.service_type or '').lower()),
            service_rows[0]
        )
        # Enhanced redo calculation with validation
        collected = float(primary_row.total_cost or 0.0)
        if collected > 0:
            # Apply rectification discount policy (10% discount for customer satisfaction)
            return round(collected * 0.90, 2)  # 10% customer satisfaction discount

        return round(max((float(row.total_cost or 0.0) for row in service_rows), default=0.0) * 0.90, 2)

    def compute_non_hair_product_cost(service_name, base_amount):
        service = (service_name or '').strip().title()
        amount = max(0.0, float(base_amount or 0.0))
        # Enhanced product cost calculation with rectification adjustments
        cost_rates = {
            'Wash': 0.40,
            'Nails': 0.30,
            'Makeup': 0.30,
            'Hair': 0.25,  # Added hair services
            'Undo': 0.15   # Reduced cost for undo services
        }
        return round(amount * cost_rates.get(service, 0.25), 2)
    
    # Enhanced data fetching with tenant isolation
    recent_work = Appointment.query.filter_by(branch=branch, salon_id=current_user.salon_id)\
        .filter(Appointment.appointment_time >= datetime.utcnow() - timedelta(days=30))\
        .order_by(Appointment.appointment_time.desc()).limit(50).all()

    appointment_service_map = {}
    appointment_service_details_map = {}
    for work in recent_work:
        lookup_key = (work.receipt_no or f"ID:{work.id}").strip()
        if work.receipt_no:
            visit_rows = Appointment.query.filter(
                Appointment.branch == branch,
                Appointment.salon_id == current_user.salon_id,
                Appointment.receipt_no == work.receipt_no,
                or_(
                    Appointment.is_redo.is_(False),
                    Appointment.is_redo.is_(None)
                )
            ).all()
        else:
            visit_rows = [work]

        normalized_services = []
        service_rows_by_name = {}
        for visit_row in visit_rows:
            normalized_name = normalize_rectification_service(visit_row.service_type, visit_row.department)
            if normalized_name and normalized_name not in normalized_services:
                normalized_services.append(normalized_name)
            if normalized_name:
                service_rows_by_name.setdefault(normalized_name, []).append(visit_row)

        appointment_service_map[lookup_key] = normalized_services

        details = {}
        for service_name, rows in service_rows_by_name.items():
            front_row = next(
                (row for row in rows if 'assistant' not in (row.service_type or '').lower()),
                rows[0]
            )
            back_row = next(
                (row for row in rows if 'assistant' in (row.service_type or '').lower()),
                None
            )
            primary_label = (front_row.service_type or '').replace(' (Assistant)', '').strip() if front_row else ''
            service_template = Service.query.filter(
                func.lower(Service.name) == primary_label.lower(),
                Service.salon_id == current_user.salon_id
            ).first() if primary_label else None
            details[service_name] = {
                'redo_amount': round(compute_redo_amount(rows), 2),
                'front_worker_id': int(front_row.worker_id) if front_row and front_row.worker_id else None,
                'back_worker_id': int(back_row.worker_id) if back_row and back_row.worker_id else None,
                'prior_product_cost': round(sum(float(r.product_cost or 0.0) for r in rows), 2),
                'template_category': (service_template.category if service_template else None),
                'template_commission_front': float(service_template.commission_front or 0.0) if service_template else None,
                'template_commission_back': float(service_template.commission_back or 0.0) if service_template else None,
                # Used by preview to show Redo clawback of already-paid original commissions.
                'prior_commission_paid': round(sum(float(r.commission_earned or 0.0) for r in rows), 2)
            }
        appointment_service_details_map[lookup_key] = details

    staff = Worker.query.filter(
        Worker.branch == branch,
        Worker.salon_id == current_user.salon_id,
        Worker.role.in_(['salonist', 'Braider'])
    ).order_by(Worker.full_name).all()

    if request.method == 'POST':
        try:
            def setup_rectification_log_target():
                """Resolve active rectification log table (legacy or current) and ensure availability."""
                inspector = inspect(db.engine)
                table_names = set(inspector.get_table_names())

                if 'rectification_logs' in table_names:
                    return {'mode': 'orm'}

                if 'rectification_log' in table_names:
                    legacy_table = Table('rectification_log', MetaData(), autoload_with=db.engine)
                    return {'mode': 'legacy', 'table': legacy_table}

                # No rectification log table exists yet; create the model-backed one.
                RectificationLog.__table__.create(bind=db.engine, checkfirst=True)
                return {'mode': 'orm'}

            def persist_rectification_log(log_target, payload):
                if log_target.get('mode') == 'legacy':
                    legacy_table = log_target['table']
                    filtered_payload = {
                        key: value
                        for key, value in payload.items()
                        if key in legacy_table.c
                    }
                    db.session.execute(legacy_table.insert().values(**filtered_payload))
                    return

                db.session.add(RectificationLog(**payload))

            log_target = setup_rectification_log_target()

            selected_lookup = (request.form.get('original_receipt_no') or request.form.get('original_appointment_id') or '').strip()
            service_types = request.form.getlist('service_type[]')
            stylist_ids = request.form.getlist('stylist_id[]')
            back_stylist_ids = request.form.getlist('back_stylist_id[]')
            amounts = request.form.getlist('amount[]')
            complained_services = request.form.getlist('complained_service[]')

            if not selected_lookup:
                flash("Please select a receipt.", "warning")
                return redirect(url_for('accountant.service_rectification'))

            original_appointment = None
            if selected_lookup.startswith('ID:'):
                fallback_id = selected_lookup.split(':', 1)[1].strip()
                if fallback_id.isdigit():
                    original_appointment = db.session.get(Appointment, int(fallback_id))
            else:
                original_appointment = Appointment.query.filter(
                    Appointment.branch == branch,
                    Appointment.salon_id == current_user.salon_id,
                    Appointment.receipt_no == selected_lookup
                ).order_by(Appointment.appointment_time.desc()).first()

            if not original_appointment:
                flash("Selected receipt was not found.", "danger")
                return redirect(url_for('accountant.service_rectification'))

            if original_appointment.receipt_no:
                visit_rows = Appointment.query.filter(
                    Appointment.branch == branch,
                    Appointment.salon_id == current_user.salon_id,
                    Appointment.receipt_no == original_appointment.receipt_no,
                    or_(
                        Appointment.is_redo.is_(False),
                        Appointment.is_redo.is_(None)
                    )
                ).all()
            else:
                visit_rows = [original_appointment]

            allowed_services = {
                normalize_rectification_service(row.service_type, row.department)
                for row in visit_rows
                if normalize_rectification_service(row.service_type, row.department)
            }

            if not any((st == 'Redo') for st in service_types):
                flash("Select at least one row with Redo type.", "warning")
                return redirect(url_for('accountant.service_rectification'))

            complaint_scope_services = {
                (svc or '').strip().title()
                for st, svc in zip(service_types, complained_services)
                if st in ['Undo', 'Wash'] and (svc or '').strip()
            }

            def map_department(service_name):
                value = (service_name or '').strip().lower()
                if value == 'hair':
                    return 'Hair'
                if value == 'wash':
                    return 'Wash'
                if value == 'makeup':
                    return 'Makeup'
                if value == 'nails':
                    return 'Nails'
                return original_appointment.department or 'Hair'

            def get_primary_service_label(service_rows):
                primary_row = next(
                    (row for row in service_rows if 'assistant' not in (row.service_type or '').lower()),
                    service_rows[0] if service_rows else None
                )
                if not primary_row:
                    return ''
                label = (primary_row.service_type or '').strip()
                return label.replace(' (Assistant)', '').strip()

            def find_service_template(service_rows, fallback_service_name=''):
                service_label = get_primary_service_label(service_rows) or (fallback_service_name or '').strip()
                if not service_label:
                    return None
                
                # First try exact match
                service = Service.query.filter(
                    func.lower(Service.name) == service_label.lower(),
                    Service.salon_id == current_user.salon_id
                ).first()
                
                # If not found, try to find similar service in same category
                if not service:
                    # Try to find any service in the same category
                    normalized_label = normalize_rectification_service(service_label)
                    similar_services = Service.query.filter(
                        Service.salon_id == current_user.salon_id,
                        Service.category.ilike(f"%{normalized_label}%")
                    ).all()
                    
                    if similar_services:
                        service = similar_services[0]  # Use first available similar service
                
                return service

            def compute_non_hair_redo_commissions(service_rows, fallback_service_name, gross_amount, use_dual_assignment):
                """Non-hair redo uses template rates if available, otherwise falls back to department defaults."""
                service_template = find_service_template(service_rows, fallback_service_name)
                
                if service_template:
                    commission_rate = service_template.commission_front or 0.0
                    front_commission = gross_amount * (commission_rate / 100.0)
                    back_commission = 0.0
                    if use_dual_assignment and service_template.commission_back:
                        back_commission = gross_amount * (service_template.commission_back / 100.0)
                    salon_share = gross_amount - front_commission - back_commission
                    product_cost = compute_non_hair_product_cost(fallback_service_name, gross_amount)
                    return front_commission, back_commission, salon_share, product_cost
                else:
                    # Fallback to department-based commission if no template found
                    service_name = (fallback_service_name or '').strip().title()
                    if service_name == 'Wash':
                        front_commission = gross_amount * 0.30
                        back_commission = 0.0
                        salon_share = gross_amount * 0.30
                        product_cost = gross_amount * 0.40
                    elif service_name in ['Nails', 'Makeup']:
                        front_commission = gross_amount * 0.35
                        back_commission = 0.0
                        salon_share = gross_amount * 0.35
                        product_cost = gross_amount * 0.30
                    else:
                        # Default for unknown services or services not offered by this tenant
                        front_commission = gross_amount * 0.40
                        back_commission = 0.0
                        salon_share = gross_amount * 0.30
                        product_cost = gross_amount * 0.30
                    return front_commission, back_commission, salon_share, product_cost

            def compute_redo_commissions(service_rows, fallback_service_name, gross_amount, extension_cost, use_dual_hair):
                """Hair redo payout mirrors record_work: 50% stylist pool from base after extension."""
                net_after_extension = max(0.0, float(gross_amount or 0.0) - float(extension_cost or 0.0))
                commission_pool = net_after_extension * 0.5
                if use_dual_hair:
                    front_commission = commission_pool / 2.0
                    back_commission = commission_pool - front_commission
                else:
                    front_commission = commission_pool
                    back_commission = 0.0

                salon_share = max(0.0, net_after_extension - (front_commission + back_commission))
                return front_commission, back_commission, salon_share


            def deduct_from_original_commissions(service_rows, deduction_amount):
                """Allocate rectification deductions to original salonists (full recovery, no historical row mutation)."""
                if deduction_amount <= 0:
                    return 0.0, [], {}

                worker_commission_pool = {}
                worker_order = []
                for row in service_rows:
                    if not row.worker_id:
                        continue
                    wid = int(row.worker_id)
                    worker_commission_pool[wid] = worker_commission_pool.get(wid, 0.0) + float(row.commission_earned or 0.0)
                    if wid not in worker_order:
                        worker_order.append(wid)

                if not worker_order:
                    return 0.0, [], {}

                deduction_allocations = {}
                total_deduction = float(deduction_amount)

                positive_pool_total = sum(v for v in worker_commission_pool.values() if v > 0)
                if positive_pool_total > 0:
                    allocated = 0.0
                    positive_workers = [wid for wid in worker_order if worker_commission_pool.get(wid, 0.0) > 0]
                    for idx, wid in enumerate(positive_workers):
                        if idx == len(positive_workers) - 1:
                            share = max(0.0, total_deduction - allocated)
                        else:
                            ratio = worker_commission_pool[wid] / positive_pool_total
                            share = round(total_deduction * ratio, 2)
                            allocated += share
                        deduction_allocations[wid] = deduction_allocations.get(wid, 0.0) + share
                else:
                    # If original rows have zero commission values, recover from recorded workers equally.
                    equal_share = round(total_deduction / len(worker_order), 2)
                    allocated = 0.0
                    for idx, wid in enumerate(worker_order):
                        if idx == len(worker_order) - 1:
                            share = max(0.0, total_deduction - allocated)
                        else:
                            share = equal_share
                            allocated += share
                        deduction_allocations[wid] = deduction_allocations.get(wid, 0.0) + share

                penalized_ids = [str(wid) for wid, amount in deduction_allocations.items() if amount > 0]
                deducted_total = sum(deduction_allocations.values())
                return deducted_total, penalized_ids, deduction_allocations

            def recover_original_paid_commissions(service_rows):
                """Recover exactly what each original worker was paid for the complained service rows."""
                commission_allocations = {}
                for row in service_rows:
                    if not row.worker_id:
                        continue
                    paid_amount = max(0.0, float(row.commission_earned or 0.0))
                    if paid_amount <= 0:
                        continue
                    worker_id = int(row.worker_id)
                    commission_allocations[worker_id] = commission_allocations.get(worker_id, 0.0) + paid_amount

                penalized_ids = [str(worker_id) for worker_id, amount in commission_allocations.items() if amount > 0]
                recovered_total = sum(commission_allocations.values())
                return recovered_total, penalized_ids, commission_allocations

            def merge_deduction_allocations(target_allocations, source_allocations):
                for worker_id, amount_value in (source_allocations or {}).items():
                    target_allocations[worker_id] = target_allocations.get(worker_id, 0.0) + float(amount_value or 0.0)

            rectification_anchor_id = None
            deduction_summaries = []
            rectification_week_start = get_week_start(datetime.utcnow())
            processed_rows = 0

            row_count = max(len(service_types), len(stylist_ids), len(amounts), len(complained_services))
            for idx in range(row_count):
                svc_type = (service_types[idx] if idx < len(service_types) else '').strip()
                s_id = (stylist_ids[idx] if idx < len(stylist_ids) else '').strip()
                back_s_id = (back_stylist_ids[idx] if idx < len(back_stylist_ids) else '').strip()
                amt = amounts[idx] if idx < len(amounts) else '0'
                complained_service = complained_services[idx] if idx < len(complained_services) else ''

                # Skip completely empty rows, but fail fast on partially filled rows.
                if not svc_type and not s_id and not (complained_service or '').strip():
                    continue
                if not s_id or not svc_type:
                    flash(f"Row {idx + 1} is incomplete. Select both Type and Front Salonist.", "danger")
                    db.session.rollback()
                    return redirect(url_for('accountant.service_rectification'))
                
                amt_val = float(amt or 0)
                service_name = (complained_service or '').strip().title()

                if service_name not in allowed_services:
                    flash(f"{service_name} is not part of the selected visit.", "danger")
                    db.session.rollback()
                    return redirect(url_for('accountant.service_rectification'))

                if svc_type == 'Redo' and complaint_scope_services and service_name not in complaint_scope_services:
                    flash(f"Redo must match complained service type(s): {', '.join(sorted(complaint_scope_services))}.", "danger")
                    db.session.rollback()
                    return redirect(url_for('accountant.service_rectification'))

                service_rows = [
                    row for row in visit_rows
                    if normalize_rectification_service(row.service_type, row.department) == service_name
                ]

                # Rectification replaces the complained service rows in analysis views.
                for original_service_row in service_rows:
                    original_service_row.is_rectified = True

                redo_appointment_id = original_appointment.id
                row_created_appointment_id = None
                target_salonist_id = int(s_id)
                penalty_value = 0.0
                penalized_ids = []
                penalty_allocations = {}
                product_penalty_allocations = {}
                commission_penalty_allocations = {}

                if svc_type == 'Redo':
                    redo_amount = compute_redo_amount(service_rows)
                    if redo_amount <= 0:
                        redo_amount = amt_val

                    extension_cost = 0.0
                    rate_product_cost = 0.0
                    if service_name == 'Hair':
                        extension_product_ids = request.form.getlist(f'redo_product_id[{idx}][]')
                        extension_qtys = request.form.getlist(f'redo_product_qty[{idx}][]')

                        for ext_pos, (product_id_raw, product_qty_raw) in enumerate(zip(extension_product_ids, extension_qtys), start=1):
                            if not product_id_raw or not str(product_id_raw).isdigit():
                                continue

                            qty_used = max(0, int(float(product_qty_raw or 0)))
                            if qty_used <= 0:
                                continue

                            redo_product = db.session.get(Product, int(product_id_raw))
                            if not redo_product or redo_product.branch != branch or redo_product.salon_id != current_user.salon_id:
                                flash('Invalid extension item selected for redo.', 'danger')
                                db.session.rollback()
                                return redirect(url_for('accountant.service_rectification'))
                            if redo_product.stock_quantity < qty_used:
                                flash(f"Insufficient stock for extension '{redo_product.name}'.", 'danger')
                                db.session.rollback()
                                return redirect(url_for('accountant.service_rectification'))

                            line_cost = float(redo_product.unit_price or 0.0) * qty_used
                            extension_cost += line_cost
                            redo_product.stock_quantity = max(0, redo_product.stock_quantity - qty_used)

                            redo_usage_txn = ProductTransaction(
                                transaction_no=f"RDO-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{redo_product.id}-{idx}-{ext_pos}"[:50],
                                product_id=redo_product.id,
                                worker_id=int(s_id),
                                quantity=qty_used,
                                total_amount=line_cost,
                                department='Hair',
                                transaction_type='Internal Use',
                                timestamp=datetime.utcnow(),
                                appointment_id=original_appointment.id
                            )
                            db.session.add(redo_usage_txn)
                    else:
                        # Keep non-hair redo product costing aligned with record_work rates.
                        rate_product_cost = compute_non_hair_product_cost(service_name, redo_amount)

                    # Recover product cost from original team.
                    # Hair rule: recover the original wasted extension/product cost from the
                    # previous salonist team (not the new redo extension usage).
                    # Non-hair keeps percentage-based product recovery.
                    if service_name == 'Hair':
                        row_product_penalty = sum(float(row.product_cost or 0.0) for row in service_rows)
                    else:
                        row_product_penalty = rate_product_cost
                    total_row_deduction = 0.0
                    if row_product_penalty > 0:
                        product_deducted, _, product_allocations = deduct_from_original_commissions(service_rows, row_product_penalty)
                        total_row_deduction += product_deducted
                        merge_deduction_allocations(product_penalty_allocations, product_allocations)
                        merge_deduction_allocations(penalty_allocations, product_allocations)

                    # Recover original paid commission when the same complained service is redone.
                    # This keeps weekly payout accurate instead of paying both original and redo commissions.
                    prior_commission_paid = sum(float(row.commission_earned or 0.0) for row in service_rows)
                    if prior_commission_paid > 0:
                        if service_name == 'Hair':
                            # Hair logic: reclaim commission from the labor base after new extension usage.
                            reclaimable_base = max(0.0, float(redo_amount or 0.0) - float(extension_cost or 0.0))
                            commission_recovery_target = min(prior_commission_paid, reclaimable_base * 0.5)
                            commission_deducted, _, commission_allocations = deduct_from_original_commissions(
                                service_rows,
                                commission_recovery_target
                            )
                        else:
                            commission_deducted, _, commission_allocations = recover_original_paid_commissions(service_rows)

                        total_row_deduction += commission_deducted
                        merge_deduction_allocations(commission_penalty_allocations, commission_allocations)
                        merge_deduction_allocations(penalty_allocations, commission_allocations)

                    if penalty_allocations:
                        penalty_value = float(sum(penalty_allocations.values()) or total_row_deduction)
                        penalized_ids = [str(worker_id) for worker_id, amount_value in penalty_allocations.items() if float(amount_value or 0.0) > 0]

                    front_worker_id = int(s_id)
                    back_worker_id = int(back_s_id) if back_s_id and str(back_s_id).isdigit() else None

                    suggested_front = next(
                        (row for row in service_rows if 'assistant' not in (row.service_type or '').lower() and row.worker_id),
                        None
                    )
                    suggested_back = next(
                        (row for row in service_rows if 'assistant' in (row.service_type or '').lower() and row.worker_id),
                        None
                    )
                    if suggested_front and not front_worker_id:
                        front_worker_id = int(suggested_front.worker_id)

                    use_dual_assignment = bool(back_worker_id and back_worker_id != front_worker_id)

                    if service_name == 'Hair':
                        front_commission, back_commission, salon_share = compute_redo_commissions(
                            service_rows=service_rows,
                            fallback_service_name=service_name,
                            gross_amount=redo_amount,
                            extension_cost=extension_cost,
                            use_dual_hair=use_dual_assignment
                        )
                    else:
                        front_commission, back_commission, salon_share, rate_product_cost = compute_non_hair_redo_commissions(
                            service_rows=service_rows,
                            fallback_service_name=service_name,
                            gross_amount=redo_amount,
                            use_dual_assignment=use_dual_assignment
                        )

                    # If redo is assigned to an original paid stylist, do not pay redo commission again.
                    original_worker_ids = {
                        int(row.worker_id)
                        for row in service_rows
                        if row.worker_id
                    }
                    payout_pool_before_guard = front_commission + back_commission + salon_share
                    if front_worker_id in original_worker_ids:
                        front_commission = 0.0
                    if use_dual_assignment and back_worker_id in original_worker_ids:
                        back_commission = 0.0
                    salon_share = max(0.0, payout_pool_before_guard - (front_commission + back_commission))

                    redo_entry = Appointment(
                        appointment_time=datetime.utcnow(),
                        service_type=f"Redo - {service_name or 'Service'}",
                        transacted_total=0.0,
                        total_cost=0.0,
                        product_cost=extension_cost + rate_product_cost,
                        commission_earned=front_commission,
                        salon_cut=salon_share,
                        salon_surplus=0.0,
                        payment_method='Redo/Internal',
                        receipt_no=original_appointment.receipt_no,
                        is_model=False,
                        parent_id=rectification_anchor_id or original_appointment.id,
                        is_redo=True,
                        is_rectified=False,
                        is_payer=False,
                        branch=branch,
                        department=map_department(service_name),
                        client_id=original_appointment.client_id,
                        worker_id=front_worker_id,
                        status='Completed',
                        notes=f"Rectification redo for original appointment #{original_appointment.id} ({service_name or 'Service'})"
                    )
                    db.session.add(redo_entry)
                    db.session.flush()
                    redo_appointment_id = redo_entry.id
                    row_created_appointment_id = redo_entry.id
                    if not rectification_anchor_id:
                        rectification_anchor_id = redo_entry.id

                    if use_dual_assignment:
                        back_redo_entry = Appointment(
                            appointment_time=datetime.utcnow(),
                            service_type=f"Redo - {service_name or 'Service'}",
                            transacted_total=0.0,
                            total_cost=0.0,
                            product_cost=extension_cost + rate_product_cost,
                            commission_earned=front_commission,
                            salon_cut=salon_share,
                            salon_surplus=0.0,
                            payment_method='Redo/Internal',
                            receipt_no=original_appointment.receipt_no,
                            is_model=False,
                            parent_id=rectification_anchor_id or original_appointment.id,
                            is_redo=True,
                            is_rectified=False,
                            is_payer=False,
                            branch=branch,
                            salon_id=current_user.salon_id,
                            department=map_department(service_name),
                            client_id=original_appointment.client_id,
                            worker_id=front_worker_id,
                            status='Completed',
                            notes=f"Rectification redo for original appointment #{original_appointment.id} ({service_name or 'Service'})"
                        )
                        db.session.add(back_redo_entry)

                    # Original team should not be charged by redo labor split.
                    # Only explicit penalties apply: Undo/Wash prep deductions and redo product costs.

                    original_appointment.is_rectified = True

                if svc_type in ['Undo', 'Wash']:
                    prep_amount = max(0.0, amt_val)
                    prep_entry = Appointment(
                        appointment_time=datetime.utcnow(),
                        service_type=f"Redo Prep - {svc_type} ({service_name or 'Service'})",
                        transacted_total=0.0,
                        total_cost=0.0,
                        product_cost=0.0,
                        commission_earned=prep_amount,
                        salon_cut=0.0,
                        salon_surplus=0.0,
                        payment_method='Redo/Internal',
                        receipt_no=original_appointment.receipt_no,
                        is_model=False,
                        parent_id=rectification_anchor_id or original_appointment.id,
                        is_redo=True,
                        is_rectified=False,
                        is_payer=False,
                        branch=branch,
                        department=map_department(service_name),
                        client_id=original_appointment.client_id,
                        worker_id=target_salonist_id,
                        status='Completed',
                        notes=f"Rectification prep ({svc_type}) for original appointment #{original_appointment.id} ({service_name or 'Service'})"
                    )
                    db.session.add(prep_entry)
                    db.session.flush()
                    row_created_appointment_id = prep_entry.id
                    if not rectification_anchor_id:
                        rectification_anchor_id = prep_entry.id

                    penalty_value, penalized_ids, penalty_allocations = deduct_from_original_commissions(service_rows, prep_amount)
                    redo_appointment_id = prep_entry.id

                if svc_type == 'Redo':
                    for worker_id, worker_amount in product_penalty_allocations.items():
                        if float(worker_amount or 0.0) <= 0:
                            continue
                        db.session.add(StaffDeduction(
                            worker_id=int(worker_id),
                            branch=branch,
                            deduction_type='inventory_issue',
                            amount=float(worker_amount),
                            product_name=f"Rectification Product Recovery - {service_name or 'Service'}",
                            reason=(
                                "Rectification product recovery (treated as product sold to salonist) | "
                                f"service: {service_name or 'Service'} | "
                                f"receipt: {original_appointment.receipt_no or f'ID:{original_appointment.id}'}"
                            ),
                            week_start=rectification_week_start
                        ))

                    for worker_id, worker_amount in commission_penalty_allocations.items():
                        if float(worker_amount or 0.0) <= 0:
                            continue
                        db.session.add(StaffDeduction(
                            worker_id=int(worker_id),
                            branch=branch,
                            deduction_type='service_rectification',
                            amount=float(worker_amount),
                            reason=(
                                "Service rectification (redo_commission_recovery) | "
                                f"service: {service_name or 'Service'} | "
                                f"receipt: {original_appointment.receipt_no or f'ID:{original_appointment.id}'}"
                            ),
                            week_start=rectification_week_start
                        ))
                elif penalty_allocations:
                    deduction_context = f'redo_prep_{svc_type.lower()}'
                    for worker_id, worker_amount in penalty_allocations.items():
                        if float(worker_amount or 0.0) <= 0:
                            continue
                        db.session.add(StaffDeduction(
                            worker_id=int(worker_id),
                            branch=branch,
                            deduction_type='service_rectification',
                            amount=float(worker_amount),
                            reason=(
                                f"Service rectification ({deduction_context}) | "
                                f"service: {service_name or 'Service'} | "
                                f"receipt: {original_appointment.receipt_no or f'ID:{original_appointment.id}'}"
                            ),
                            week_start=rectification_week_start
                        ))
                
                log_payload = {
                    'original_appointment_id': original_appointment.id,
                    'redo_appointment_id': rectification_anchor_id or row_created_appointment_id or redo_appointment_id,
                    'prep_labor_penalty': penalty_value,
                    'penalized_salonist_ids': ','.join(penalized_ids),
                    'undo_salonist_id': target_salonist_id if svc_type == 'Undo' else None,
                    'wash_salonist_id': target_salonist_id if svc_type == 'Wash' else None,
                    'created_at': datetime.utcnow()
                }
                persist_rectification_log(log_target, log_payload)

                deduction_summaries.append({
                    'type': svc_type,
                    'service': service_name or 'Service',
                    'deduction': float(penalty_value or 0.0),
                    'count': len(penalized_ids)
                })
                processed_rows += 1

            if processed_rows == 0:
                flash("No valid rectification rows were submitted.", "warning")
                db.session.rollback()
                return redirect(url_for('accountant.service_rectification'))

            db.session.commit()
            flash("Service rectification saved.", "success")
            if deduction_summaries:
                session['rectification_deduction_summary'] = {
                    'receipt_no': original_appointment.receipt_no or f"ID:{original_appointment.id}",
                    'total': round(sum(item['deduction'] for item in deduction_summaries), 2),
                    'rows': deduction_summaries
                }
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Rectification Error: {e}")
            flash(f"Error: {str(e)}", "danger")
        
        return redirect(url_for('accountant.service_rectification'))

    deduction_summary = session.pop('rectification_deduction_summary', None)

    return render_template(
        'accountant/service_rectification.html',
        recent_work=recent_work,
        staff=staff,
        deduction_summary=deduction_summary,
        products=Product.query.filter(
            Product.branch == branch,
            or_(
                Product.department.in_(['Hair', 'Salon']),
                Product.category.in_(['Hair', 'Extension', 'Braid'])
            )
        ).order_by(Product.name.asc()).all(),
        appointment_service_map=appointment_service_map,
        appointment_service_details_map=appointment_service_details_map
    )

# --- SERVICE ORDERS ---

@accountant_bp.route('/service-orders')
@login_required
@roles_required('accountant')
def service_orders():
    """Display all service orders"""
    branch = current_user.branch
    status_filter = request.args.get('status')
    
    query = ServiceOrder.query.filter_by(branch=branch)
    
    # Default to pending orders unless explicitly filtered
    if status_filter:
        query = query.filter_by(status=status_filter)
    else:
        query = query.filter_by(status='pending')
    
    orders = query.order_by(ServiceOrder.created_at.desc()).all()
    return render_template('accountant/service_orders.html', orders=orders)

@accountant_bp.route('/service-order/new', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def new_service_order():
    """Create a new service order"""
    if request.method == 'POST':
        client_name = request.form.get('client_name')
        client_phone = request.form.get('client_phone')
        branch = current_user.branch
        
        # Create new service order
        service_order = ServiceOrder(
            client_name=client_name,
            client_phone=client_phone,
            branch=branch,
            created_by_id=current_user.id,
            status='pending'
        )
        
        db.session.add(service_order)
        db.session.commit()
        
        flash('Service order created successfully!', 'success')
        return redirect(url_for('accountant.service_orders'))
    
    return render_template('accountant/new_service_order.html')

@accountant_bp.route('/service-order/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def edit_service_order(order_id):
    """Edit service order to add payment details"""
    service_order = ServiceOrder.query.get_or_404(order_id)
    
    if request.method == 'POST':
        service_order.transacted_total = float(request.form.get('transacted_total', 0))
        service_order.payment_method = request.form.get('payment_method')
        service_order.receipt_no = request.form.get('receipt_no')
        service_order.is_model = request.form.get('is_model') == 'on'
        service_order.status = 'paid'
        service_order.paid_at = datetime.utcnow()
        
        db.session.commit()
        flash('Payment details updated successfully!', 'success')
        return redirect(url_for('accountant.service_orders'))
    
    # Get tenant-specific payment options
    payment_options = get_tenant_payment_options(current_user.salon_id)
    
    return render_template('accountant/edit_service_order.html', 
                         order=service_order,
                         payment_options=payment_options)

@accountant_bp.route('/service-order/<int:order_id>/delete', methods=['POST'])
@login_required
@roles_required('accountant')
def delete_service_order(order_id):
    """Delete a service order"""
    service_order = ServiceOrder.query.get_or_404(order_id)
    
    if service_order.status != 'pending':
        flash('Cannot delete a service order that is not pending!', 'error')
        return redirect(url_for('accountant.service_orders'))
    
    db.session.delete(service_order)
    db.session.commit()
    flash('Service order deleted successfully!', 'success')
    return redirect(url_for('accountant.service_orders'))

@accountant_bp.route('/service-order/<int:order_id>/record-services', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def record_services(order_id):
    """Record services for a paid service order using the existing record work system"""
    service_order = ServiceOrder.query.get_or_404(order_id)
    
    if service_order.status != 'paid':
        flash('Can only record services for paid orders!', 'error')
        return redirect(url_for('accountant.service_orders'))
    
    if request.method == 'POST':
# DEBUG:         print(f"DEBUG: Form submitted for order {order_id}")
# DEBUG:         print(f"DEBUG: Form keys: {list(request.form.keys())}")
        
        # Use the working logic from record_work, adapted for service orders
        receipt_no = request.form.get('receipt_no') or service_order.receipt_no
        transacted_total_raw = request.form.get('transacted_total') or str(service_order.transacted_total or 0)
        payment_method = request.form.get('payment_method') or service_order.payment_method

        if not receipt_no or (not transacted_total_raw and payment_method != 'Model/Internal'):
            flash("Error: Receipt Number and Grand Total are required.", "danger")
            return redirect(url_for('accountant.record_services', order_id=order_id))
        
        try:
            transacted_total = float(transacted_total_raw or 0)
        except ValueError:
            transacted_total = 0.0

        if Appointment.query.filter_by(receipt_no=receipt_no).first():
            flash(f"Error: Receipt #{receipt_no} has already been recorded.", "danger")
            return redirect(url_for('accountant.record_services', order_id=order_id))

        date_str = request.form.get('appointment_date')
        client_input = request.form.get('client_id') 

        if date_str:
            try:
                selected_date = datetime.strptime(date_str, '%Y-%m-%d')
                final_timestamp = datetime.combine(selected_date, datetime.utcnow().time())
            except ValueError:
                final_timestamp = datetime.utcnow()
        else:
            final_timestamp = datetime.utcnow()

        # Use service order client or create new one
        target_client_id = service_order.client_id
        if not target_client_id:
            normalized_client_input = (client_input or service_order.client_name or '').strip()
            if normalized_client_input:
                existing_c = None

                if normalized_client_input.isdigit():
                    existing_c = Client.query.filter_by(id=int(normalized_client_input), branch=service_order.branch).first()
                    if not existing_c:
                        existing_c = Client.query.filter_by(phone=normalized_client_input, branch=service_order.branch).first()
                else:
                    existing_c = Client.query.filter(
                        (Client.full_name == normalized_client_input) | (Client.phone == normalized_client_input),
                        Client.branch == service_order.branch
                    ).first()

                if existing_c:
                    target_client_id = existing_c.id
                else:
                    new_c = Client(
                        full_name=normalized_client_input if not normalized_client_input.isdigit() else f"Client {normalized_client_input}",
                        phone=normalized_client_input if normalized_client_input.isdigit() else "N/A",
                        branch=service_order.branch
                    )
                    db.session.add(new_c)
                    db.session.flush()
                    target_client_id = new_c.id
                    service_order.client_id = target_client_id

        front_workers = request.form.getlist('front_worker_id[]')
        back_workers = request.form.getlist('back_worker_id[]')
        service_types = request.form.getlist('service_type[]')
        
        all_prices = request.form.getlist('price[]') 
        
        f_comms = request.form.getlist('comm_front[]')
        b_comms = request.form.getlist('comm_back[]')
        pricing_scenes = request.form.getlist('pricing_scene[]')
        final_bases = request.form.getlist('final_base_price[]')

        shop_p_ids = request.form.getlist('shop_product_id[]')
        shop_p_qtys = request.form.getlist('shop_product_qty[]')

# DEBUG:         print(f"DEBUG: Processing {len(front_workers)} workers...")

# DEBUG:         print("DEBUG: Starting service processing loop...")
        try:
            for i in range(len(front_workers)):
                if not front_workers[i]:
# DEBUG:                     print(f"DEBUG: Skipping worker {i} - no front worker assigned")
                    continue

# DEBUG:                 print(f"DEBUG: Processing worker {i}: {front_workers[i]}")
                
                try:
                    total_cost = float(all_prices[i] or 0)
                except (IndexError, ValueError):
                    total_cost = 0.0
                
                service_name_lower = service_types[i].lower()
                comm_f = float(f_comms[i] or 0)
                comm_b = float(b_comms[i] or 0)
                total_row_commissions = comm_f + comm_b

# DEBUG:                 print(f"DEBUG: Service: {service_types[i]}, Cost: {total_cost}, Comm_F: {comm_f}, Comm_B: {comm_b}")

                current_dept = "Hair"
                row_product_cost = 0.0
                row_salon_cut = 0.0
                salon_surplus = 0.0

                if "wash" in service_name_lower:
                    current_dept = "Wash"
                elif "nail" in service_name_lower:
                    current_dept = "Nails"
                elif "makeup" in service_name_lower:
                    current_dept = "Makeup"
                else:
                    current_dept = "Hair"

# DEBUG:                 print(f"DEBUG: Department: {current_dept}")

                nested_p_ids = request.form.getlist(f'nested_product_id[{i}][]')
                nested_p_qtys = request.form.getlist(f'nested_product_qty[{i}][]')
                for p_id, p_qty in zip(nested_p_ids, nested_p_qtys):
                    if p_id and p_qty and int(p_qty) > 0:
                        product = db.session.get(Product, int(p_id))
                        if product:
                            row_product_cost += (product.unit_price * int(p_qty))
                            product.stock_quantity = max(0, product.stock_quantity - int(p_qty))

                if current_dept == "Hair":
                    scene = pricing_scenes[i] if i < len(pricing_scenes) else "Scene 1"
                    if "Scene 2" in scene:
                        labor_base = float(final_bases[i] or 0) if i < len(final_bases) else 0.0
                        row_salon_cut = labor_base - total_row_commissions
                        salon_surplus = total_cost - labor_base - row_product_cost
                    else:
                        calculated_labor_base = total_cost - row_product_cost
                        row_salon_cut = calculated_labor_base - total_row_commissions
                        salon_surplus = 0.0
                else:
                    if current_dept == "Wash":
                        row_salon_cut = total_cost * 0.30
                        row_product_cost = total_cost * 0.40
                    elif current_dept in ["Nails", "Makeup"]:
                        row_salon_cut = total_cost * 0.35
                        row_product_cost = total_cost * 0.30
                    salon_surplus = 0.0

# DEBUG:                 print(f"DEBUG: Calculations - Salon Cut: {row_salon_cut}, Product Cost: {row_product_cost}, Surplus: {salon_surplus}")

                if payment_method == 'Model/Internal':
                    model_valuation = total_row_commissions + row_product_cost
# DEBUG:                     print(f"DEBUG: Adding Model/Internal expense: {model_valuation}")
                    new_expense = Expense(
                        category="Internal/Model Service",
                        amount=model_valuation,
                        expense_date=final_timestamp,
                        branch=service_order.branch,
                        month=final_timestamp.strftime('%B %Y')
                    )
                    db.session.add(new_expense)

# DEBUG:                 print(f"DEBUG: Creating front appointment for worker {front_workers[i]}")
                front_entry = Appointment(
                    receipt_no=receipt_no,
                    client_id=target_client_id, 
                    worker_id=int(front_workers[i]),
                    service_type=service_types[i],
                    department=current_dept,
                    total_cost=total_cost,
                    transacted_total=0.0 if payment_method == 'Model/Internal' else transacted_total,
                    commission_earned=comm_f,
                    salon_cut=row_salon_cut,
                    product_cost=row_product_cost,
                    salon_surplus=salon_surplus,
                    branch=service_order.branch,
                    appointment_time=final_timestamp,
                    payment_method=payment_method,
                    is_model=True if payment_method == 'Model/Internal' else False,
                    status='Completed',
                    notes=f"Service Order #{service_order.id}"
                )
                db.session.add(front_entry)
# DEBUG:                 print(f"DEBUG: Front appointment added to session")

                if i < len(back_workers) and back_workers[i]:
# DEBUG:                     print(f"DEBUG: Creating back appointment for worker {back_workers[i]}")
                    back_entry = Appointment(
                        receipt_no=receipt_no,
                        client_id=target_client_id,
                        worker_id=int(back_workers[i]),
                        service_type=f"{service_types[i]} (Assistant)",
                        department=current_dept,
                        total_cost=0.0, 
                        transacted_total=0.0 if payment_method == 'Model/Internal' else transacted_total,
                        commission_earned=comm_b,
                        salon_cut=0.0, 
                        product_cost=0.0,
                        salon_surplus=0.0, 
                        branch=service_order.branch,
                        appointment_time=final_timestamp,
                        payment_method="Split_Internal" if payment_method != 'Model/Internal' else "Model/Internal",
                        status='Completed',
                        notes=f"Assistant for Service Order #{service_order.id}"
                    )
                    db.session.add(back_entry)
# DEBUG:                     print(f"DEBUG: Back appointment added to session")
                else:
                    print(f"DEBUG: No back worker for service {i}")

            for p_id, p_qty in zip(shop_p_ids, shop_p_qtys):
                if p_id and p_qty and int(p_qty) > 0:
                    product = db.session.get(Product, int(p_id))
                    if product:
                        qty = int(p_qty)
                        shop_sale = ProductTransaction(
                            transaction_no=receipt_no,
                            product_id=product.id,
                            client_id=target_client_id,
                            quantity=qty,
                            total_amount=product.unit_price * qty,
                            transaction_type='Direct',
                            timestamp=final_timestamp,
                            notes=f"Shop purchase during Service Order #{service_order.id}"
                        )
                        product.stock_quantity = max(0, product.stock_quantity - qty)
                        db.session.add(shop_sale)

            # --- START TIP PROCESSING SECTION ---
            tip_amount_raw = request.form.get('tip_amount')
            tip_recipient_ids = request.form.getlist('tip_recipient_ids[]')
            
            try:
                total_tip = float(tip_amount_raw or 0)
            except ValueError:
                total_tip = 0.0

            if total_tip > 0 and tip_recipient_ids:
                tip_split = total_tip / len(tip_recipient_ids)
                for worker_id_str in tip_recipient_ids:
                    if worker_id_str:
                        tip_entry = Appointment(
                            receipt_no=receipt_no,
                            client_id=target_client_id,
                            worker_id=int(worker_id_str),
                            service_type="Client Tip",
                            department="Tip",
                            total_cost=0.0,
                            transacted_total=0.0 if payment_method == 'Model/Internal' else transacted_total,
                            commission_earned=0.0,
                            tips=tip_split,
                            branch=service_order.branch,
                            appointment_time=final_timestamp,
                            payment_method=payment_method,
                            status='Completed',
                            notes=f"Shared tip from Service Order #{service_order.id}"
                        )
                        db.session.add(tip_entry)
            # --- END TIP PROCESSING SECTION ---

            # Update service order status
            service_order.status = 'completed'
# DEBUG:             print("DEBUG: About to commit to database")
            db.session.commit()
# DEBUG:             print("DEBUG: Successfully committed to database")
            
            flash(f"Successfully recorded Receipt #{receipt_no} for Service Order #{service_order.id}.", "success")
            return redirect(url_for('accountant.service_orders'))

        except Exception as e:
# DEBUG:             print(f"DEBUG: Exception occurred: {e}")
            db.session.rollback()
            flash(f"Error processing entry: {str(e)}", "danger")
    
# DEBUG:     print("DEBUG: Preparing GET request data...")
    
    # Prepare data for the record_work template
    clients = Client.query.all()  # Global clients - can visit any branch
    services = Service.query.filter_by(salon_id=service_order.salon_id).order_by(Service.name.asc()).all()
    salonists = Worker.query.filter_by(role='salonist', branch=service_order.branch, salon_id=service_order.salon_id).all()
    
    # Pre-fill the form with service order data
    return render_template('accountant/record_work.html', 
                         clients=clients,
                         services=services,
                         salonists=salonists,
                         prefill_data={
                             'client_name': service_order.client_name,
                             'client_phone': service_order.client_phone,
                             'transacted_total': service_order.transacted_total,
                             'payment_method': service_order.payment_method,
                             'is_model': service_order.is_model,
                             'receipt_no': service_order.receipt_no,
                             'service_order_id': service_order.id,
                             'created_at': service_order.created_at
                         },
                         preselected_orders=[])  # Start with empty preselected orders

# --- API ENDPOINTS ---

@accountant_bp.route('/api/search-clients')
@login_required
@roles_required('accountant')
def search_clients():
    """API endpoint for client search with Select2 - Global clients"""
    query = request.args.get('q', '')
    
    clients = Client.query.filter(
        or_(
            Client.full_name.ilike(f'%{query}%'),
            Client.phone.ilike(f'%{query}%')
        )
    ).limit(10).all()
    
    results = []
    for client in clients:
        results.append({
            'id': client.id,
            'text': f"{client.full_name} - {client.phone}",
            'full_name': client.full_name,
            'phone': client.phone
        })
    
    return jsonify({'results': results})


@accountant_bp.route('/api/specialties')
@login_required
@roles_required('accountant')
def get_specialties():
    """API endpoint to get existing specialties for Select2"""
    try:
        # Get unique specialties from workers table for current branch
        specialties = db.session.query(Worker.specialty)\
            .filter(Worker.specialty.isnot(None))\
            .filter(Worker.specialty != '')\
            .filter(Worker.branch == current_user.branch)\
            .distinct()\
            .all()
        
        # Format for Select2
        results = [{'id': spec[0], 'text': spec[0]} for spec in specialties if spec[0]]
        
        return jsonify({
            'results': results,
            'pagination': {'more': False}
        })
    except Exception as e:
        current_app.logger.error(f"Error fetching specialties: {e}")
        return jsonify({'results': []}), 500


@accountant_bp.route('/api/specialties', methods=['POST'])
@login_required
@roles_required('accountant')
def add_specialty():
    """API endpoint to add a new specialty (for Select2 tagging)"""
    try:
        data = request.get_json()
        specialty_name = data.get('text', '').strip()
        
        if not specialty_name:
            return jsonify({'error': 'Specialty name is required'}), 400
        
        # Check if specialty already exists in current branch
        existing = Worker.query.filter_by(specialty=specialty_name, branch=current_user.branch).first()
        if existing:
            return jsonify({
                'id': specialty_name,
                'text': specialty_name
            })
        
        # Return the new specialty (it will be created when a worker is actually added)
        return jsonify({
            'id': specialty_name,
            'text': specialty_name
        })
        
    except Exception as e:
        current_app.logger.error(f"Error adding specialty: {e}")
        return jsonify({'error': 'Failed to add specialty'}), 500