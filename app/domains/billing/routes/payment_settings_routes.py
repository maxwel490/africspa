"""Billing routes: tenant payment settings (admin_bp)."""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import db
from app.decorators import roles_required
from app.admin import admin_bp


@admin_bp.route('/payment-settings', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def payment_settings():
    """Manage tenant payment configuration"""
    from app.domains.shared.utils import get_tenant_payment_options, save_tenant_payment_config
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_config':
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
            payment_config = {
                'enabled_methods': enabled_methods
            }
            
            if save_tenant_payment_config(current_user.salon_id, payment_config):
                flash('Payment configuration saved successfully!', 'success')
            else:
                flash('Error saving payment configuration.', 'danger')
            
            return redirect(url_for('admin.payment_settings'))
    
    # Get current configuration
    current_options = get_tenant_payment_options(current_user.salon_id)
    
    # Get all possible methods for the form
    all_methods = [
        {'code': 'mpesa', 'name': 'M-Pesa', 'icon': 'fas fa-mobile-alt'},
        {'code': 'bank', 'name': 'Bank', 'icon': 'fas fa-university'},
        {'code': 'cash', 'name': 'Cash', 'icon': 'fas fa-money-bill'},
        {'code': 'model', 'name': 'Model (No Payment)', 'icon': 'fas fa-user'},
    ]
    
    # Mark which methods are currently enabled
    enabled_codes = [opt['code'] for opt in current_options]
    
    return render_template('admin/payment_settings.html',
                         current_options=current_options,
                         all_methods=all_methods,
                         enabled_codes=enabled_codes)
