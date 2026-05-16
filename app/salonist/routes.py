from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.models import Appointment, StaffDeduction, Worker, db
from flask_login import current_user, login_required
from app.decorators import roles_required
from datetime import datetime, timedelta

salonist_bp = Blueprint('salonist', __name__)


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
    if 'nail' in value:
        return 'Nails'
    if 'wash' in value:
        return 'Wash'
    if 'makeup' in value:
        return 'Makeup'
    return 'Uncategorized'

@salonist_bp.route('/dashboard')
@login_required
@roles_required('salonist')
def dashboard():
    # Mother-to-Child architecture: Filters data by logged-in user AND their branch
    work_done = Appointment.query.filter_by(
        worker_id=current_user.id,
        branch=current_user.branch
    ).all()
    
    # Time Logic
    today = datetime.utcnow()
    # Calculate start of current week (Monday)
    start_dt = today - timedelta(days=today.weekday())
    week_start = start_dt.strftime('%b %d')
    # Calculate end of current week (Sunday) for the template badge
    week_end = (start_dt + timedelta(days=6)).strftime('%b %d')

    week_start_dt = get_week_start(today)
    week_end_dt = week_start_dt + timedelta(days=6, hours=23, minutes=59, seconds=59)

    weekly_work = Appointment.query.filter(
        Appointment.worker_id == current_user.id,
        Appointment.branch == current_user.branch,
        Appointment.appointment_time >= week_start_dt,
        Appointment.appointment_time <= week_end_dt
    ).all()
    total_earned = sum((item.commission_earned or 0.0) for item in weekly_work)

    # Auto-log monthly mandatory deduction for Conrows/Braids in 4th week of month (once per source entry)
    worker_specialty = normalize_specialty(current_user.specialty)
    if worker_specialty in ['Conrows', 'Braids']:
        due_entries = []
        for entry in StaffDeduction.query.filter_by(
            branch=current_user.branch,
            target_role='Cornrows & Braids',
            deduction_type='global_mandatory'
        ).all():
            due_week = get_fourth_sunday_week_start(entry.created_at or datetime.utcnow())
            if due_week == week_start_dt:
                due_entries.append(entry)

        conrows_braids_count = 0
        for worker in Worker.query.filter_by(branch=current_user.branch, role='salonist').all():
            if normalize_specialty(worker.specialty) in ['Conrows', 'Braids']:
                conrows_braids_count += 1
        specialists_count = max(1, conrows_braids_count)

        new_logs_created = False
        for entry in due_entries:
            reason = f"Mandatory monthly back-bar split | source:{entry.id}"
            exists = StaffDeduction.query.filter_by(
                worker_id=current_user.id,
                branch=current_user.branch,
                deduction_type='mandatory_specialty_4th_week_monthly',
                week_start=week_start_dt,
                reason=reason
            ).first()
            if not exists:
                db.session.add(StaffDeduction(
                    worker_id=current_user.id,
                    branch=current_user.branch,
                    deduction_type='mandatory_specialty_4th_week_monthly',
                    amount=float(entry.amount or 0.0) / specialists_count,
                    reason=reason,
                    week_start=week_start_dt
                ))
                new_logs_created = True
        if new_logs_created:
            db.session.commit()

    weekly_deductions = StaffDeduction.query.filter(
        StaffDeduction.worker_id == current_user.id,
        StaffDeduction.branch == current_user.branch,
        StaffDeduction.week_start == week_start_dt
    ).order_by(StaffDeduction.created_at.desc()).all()

    total_deductions = sum((d.amount or 0.0) for d in weekly_deductions)
    net_payout = max(0.0, total_earned - total_deductions)
    
    return render_template('salonist/dashboard.html', 
                           work_done=work_done, 
                           total_earned=total_earned,
                           full_history=work_done,
                           week_start=week_start,
                           week_end=week_end,
                           weekly_deductions=weekly_deductions,
                           total_deductions=total_deductions,
                           net_payout=net_payout)

# app/salonist/routes.py

@salonist_bp.route('/work')  # Standardized URL Path
@login_required
@roles_required('salonist')
def work_history():          # Standardized Function Name (The Endpoint)
    """Displays work history with active week-by-week navigation."""
    week_param = request.args.get('week')
    date_param = (request.args.get('date') or '').strip()

    if date_param:
        try:
            target_date = datetime.strptime(date_param, '%Y-%m-%d')
        except ValueError:
            target_date = datetime.utcnow()
    else:
        target_date = datetime.utcnow()

    # Week Navigation Logic
    if week_param == 'prev':
        target_date -= timedelta(days=7)
    elif week_param == 'next':
        target_date += timedelta(days=7)

    # Calculate Weekly Range (Sunday to Saturday)
    days_to_subtract = (target_date.weekday() + 1) % 7
    start_of_week = (target_date - timedelta(days=days_to_subtract)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)

    # Fetch Data: Strictly filtered by User and Branch (Mother-to-Child Logic)
    my_work = Appointment.query.filter(
        Appointment.worker_id == current_user.id,
        Appointment.branch == current_user.branch,
        Appointment.appointment_time >= start_of_week,
        Appointment.appointment_time <= end_of_week
    ).order_by(Appointment.appointment_time.desc()).all()

    # Calculate Summaries for the Cards
    total_commission = sum((w.commission_earned or 0.0) for w in my_work)
    total_tips = sum((w.tips or 0.0) for w in my_work)

    weekly_deductions = StaffDeduction.query.filter(
        StaffDeduction.worker_id == current_user.id,
        StaffDeduction.branch == current_user.branch,
        StaffDeduction.week_start == start_of_week
    ).order_by(StaffDeduction.created_at.desc()).all()

    total_deductions = sum((item.amount or 0.0) for item in weekly_deductions)
    net_weekly_payout = max(0.0, (total_commission + total_tips) - total_deductions)

    deduction_totals_by_type = {}
    for item in weekly_deductions:
        key = item.deduction_type or 'uncategorized'
        deduction_totals_by_type[key] = deduction_totals_by_type.get(key, 0.0) + float(item.amount or 0.0)

    selected_date = target_date.date().isoformat()
    prev_date = (target_date - timedelta(days=7)).date().isoformat()
    next_date = (target_date + timedelta(days=7)).date().isoformat()

    return render_template('salonist/work.html', 
                           my_work=my_work, 
                           total_commission=total_commission,
                           total_tips=total_tips,
                           total_deductions=total_deductions,
                           net_weekly_payout=net_weekly_payout,
                           weekly_deductions=weekly_deductions,
                           deduction_totals_by_type=deduction_totals_by_type,
                           start_of_week=start_of_week,
                           end_of_week=end_of_week,
                           selected_date=selected_date,
                           prev_date=prev_date,
                           next_date=next_date)