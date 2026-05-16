"""Tenancy routes: branch management, salon settings, backbar groups (admin_bp)."""
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import Salon, Worker, Branch, Product, ServiceOrder, BackbarGroup, db
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from app.decorators import roles_required
from app.admin import admin_bp
import uuid


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
    from app.domains.shared.utils import get_tenant_payment_options
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
