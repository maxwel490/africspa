"""Finance routes: commissions, staff management (accountant_bp)."""
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
