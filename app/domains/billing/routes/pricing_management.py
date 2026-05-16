"""
Pricing Management Routes for Superadmin
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.decorators import roles_required
from app.models import PricingConfig, PricingHistory
from app import db
from datetime import datetime

superadmin_pricing_bp = Blueprint('superadmin_pricing', __name__)


@superadmin_pricing_bp.route('/')
@login_required
@roles_required('superadmin')
def pricing_management():
    """Pricing management dashboard for superadmin"""
    try:
        # Get current pricing configuration
        pricing_config = PricingConfig.get_active_config()
        if not pricing_config:
            # Create default pricing config if none exists
            pricing_config = PricingConfig(
                price_per_branch_usd=30.0,
                enterprise_price_per_branch_usd=25.0,
                enterprise_min_branches=50,
                east_africa_multiplier=120.0,
                west_africa_multiplier=780.0,
                southern_africa_multiplier=18.5,
                north_africa_multiplier=48.0,
                central_africa_multiplier=552.0
            )
            db.session.add(pricing_config)
            db.session.commit()
        
        # Get pricing history
        pricing_history = PricingHistory.query.order_by(PricingHistory.changed_at.desc()).limit(10).all()
        
        return render_template('superadmin/pricing_management.html',
                             pricing_config=pricing_config,
                             pricing_history=pricing_history)
        
    except Exception as e:
        flash(f'Error loading pricing management: {str(e)}', 'danger')
        return redirect(url_for('superadmin.dashboard'))


@superadmin_pricing_bp.route('/update', methods=['POST'])
@login_required
@roles_required('superadmin')
def update_pricing():
    """Update pricing configuration"""
    try:
        # Get current pricing config
        pricing_config = PricingConfig.get_active_config()
        if not pricing_config:
            flash('No active pricing configuration found', 'danger')
            return redirect(url_for('superadmin_pricing.pricing_management'))
        
        # Store old values for history
        old_standard_price = pricing_config.price_per_branch_usd
        old_enterprise_price = pricing_config.enterprise_price_per_branch_usd
        
        # Update pricing config
        pricing_config.price_per_branch_usd = float(request.form.get('price_per_branch_usd'))
        pricing_config.enterprise_price_per_branch_usd = float(request.form.get('enterprise_price_per_branch_usd'))
        pricing_config.enterprise_min_branches = int(request.form.get('enterprise_min_branches'))
        
        # Update regional multipliers
        pricing_config.east_africa_multiplier = float(request.form.get('east_africa_multiplier'))
        pricing_config.west_africa_multiplier = float(request.form.get('west_africa_multiplier'))
        pricing_config.southern_africa_multiplier = float(request.form.get('southern_africa_multiplier'))
        pricing_config.north_africa_multiplier = float(request.form.get('north_africa_multiplier'))
        pricing_config.central_africa_multiplier = float(request.form.get('central_africa_multiplier'))
        
        pricing_config.updated_at = datetime.utcnow()
        pricing_config.updated_by = current_user.id
        
        # Create pricing history record
        pricing_history = PricingHistory(
            pricing_config_id=pricing_config.id,
            old_price_per_branch=old_standard_price,
            new_price_per_branch=pricing_config.price_per_branch_usd,
            old_enterprise_price=old_enterprise_price,
            new_enterprise_price=pricing_config.enterprise_price_per_branch_usd,
            change_reason=request.form.get('change_reason'),
            changed_by=current_user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        db.session.add(pricing_history)
        db.session.commit()
        
        # Clear pricing config cache in subscription service
        from app.services.subscription_payment import subscription_payment_service
        subscription_payment_service._pricing_config = None
        
        flash('Pricing configuration updated successfully!', 'success')
        return redirect(url_for('superadmin_pricing.pricing_management'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating pricing: {str(e)}', 'danger')
        return redirect(url_for('superadmin_pricing.pricing_management'))


@superadmin_pricing_bp.route('/api/current-pricing')
@login_required
@roles_required('superadmin')
def get_current_pricing():
    """API endpoint to get current pricing configuration"""
    try:
        pricing_config = PricingConfig.get_active_config()
        if not pricing_config:
            return jsonify({'error': 'No pricing configuration found'}), 404
        
        return jsonify({
            'price_per_branch_usd': pricing_config.price_per_branch_usd,
            'enterprise_price_per_branch_usd': pricing_config.enterprise_price_per_branch_usd,
            'enterprise_min_branches': pricing_config.enterprise_min_branches,
            'regional_multipliers': {
                'east_africa': pricing_config.east_africa_multiplier,
                'west_africa': pricing_config.west_africa_multiplier,
                'southern_africa': pricing_config.southern_africa_multiplier,
                'north_africa': pricing_config.north_africa_multiplier,
                'central_africa': pricing_config.central_africa_multiplier
            },
            'updated_at': pricing_config.updated_at.isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@superadmin_pricing_bp.route('/api/revenue-impact')
@login_required
@roles_required('superadmin')
def calculate_revenue_impact():
    """Calculate revenue impact of pricing changes"""
    try:
        from app.models import Salon, Branch
        
        # Get current active branches count
        active_branches = Branch.query.filter_by(is_active=True).count()
        enterprise_branches = 0
        
        # Count enterprise salons (50+ branches)
        for salon in Salon.query.filter_by(is_active=True).all():
            salon_branches = Branch.query.filter_by(salon_id=salon.id, is_active=True).count()
            if salon_branches >= 50:
                enterprise_branches += salon_branches
        
        standard_branches = active_branches - enterprise_branches
        
        # Get current pricing
        pricing_config = PricingConfig.get_active_config()
        if not pricing_config:
            return jsonify({'error': 'No pricing configuration found'}), 404
        
        # Calculate current monthly revenue
        current_monthly_revenue = (
            (standard_branches * pricing_config.price_per_branch_usd) +
            (enterprise_branches * pricing_config.enterprise_price_per_branch_usd)
        )
        
        return jsonify({
            'active_branches': active_branches,
            'standard_branches': standard_branches,
            'enterprise_branches': enterprise_branches,
            'current_monthly_revenue_usd': current_monthly_revenue,
            'pricing_per_branch': pricing_config.price_per_branch_usd,
            'enterprise_pricing_per_branch': pricing_config.enterprise_price_per_branch_usd
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
