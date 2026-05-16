"""Scheduling routes: service orders, record services, rectification (accountant_bp)."""
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
