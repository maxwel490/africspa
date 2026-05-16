"""Inventory routes: admin stock control and product costs (admin_bp)."""
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import (Expense, Service, Worker, Appointment, Product, ProductTransaction,
                        SupplierInvoice, MonthlyReconciliation, DepartmentCategoryConfig,
                        Branch, ServiceOrder, db)
from sqlalchemy import func
from datetime import datetime, timedelta
from app.decorators import roles_required
from app.middleware.access_control_middleware import no_inventory_access
from app.admin import admin_bp


def get_managed_branches():
    try:
        existing = Branch.query.order_by(Branch.name.asc()).all()
        return [b.name for b in existing if b.is_active]
    except Exception:
        db.session.rollback()
        return []


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
