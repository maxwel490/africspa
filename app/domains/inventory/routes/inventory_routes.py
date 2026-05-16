"""Inventory routes: products, stock, settlements, shop, back-bar (accountant_bp)."""
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
