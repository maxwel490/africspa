"""
CONTINENTAL SCALING ROUTES
Pan-African management endpoints for super admins
"""

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import Salon, Worker, Branch, Client, db
from app.decorators import roles_required
from app.continental_scaling import (
    ContinentalSubscriptionManager, 
    CurrencyConverter, 
    GeographicPartitioner,
    estimate_continental_resources,
    AFRICAN_REGIONS,
    CONTINENTAL_PLANS
)
from . import superadmin_bp

@superadmin_bp.route('/continental-dashboard')
@login_required
@roles_required('superadmin')
def continental_dashboard():
    """Pan-African scaling dashboard"""
    
    # Regional statistics
    regional_stats = {}
    total_salons = 0
    total_revenue = 0
    
    for region_key, region_config in AFRICAN_REGIONS.items():
        salons_in_region = Salon.query.filter_by(region=region_key).all()
        
        regional_stats[region_key] = {
            'name': region_config.name,
            'currency': region_config.currency,
            'salon_count': len(salons_in_region),
            'active_salons': len([s for s in salons_in_region if s.is_active]),
            'total_branches': sum(len(s.branches) for s in salons_in_region),
            'total_staff': sum(len(s.workers) for s in salons_in_region),
            'total_clients': sum(len(s.clients) for s in salons_in_region)
        }
        
        # Calculate regional revenue
        for salon in salons_in_region:
            if salon.is_subscription_active():
                pricing = salon.get_regional_pricing_info()
                if pricing:
                    regional_stats[region_key]['revenue'] = regional_stats[region_key].get('revenue', 0) + pricing['price_local']
        
        total_salons += len(salons_in_region)
    
    # Continental projections
    projections = estimate_continental_resources(10000)  # 10K salon target
    
    return render_template('superadmin/continental_dashboard.html',
                         regional_stats=regional_stats,
                         total_salons=total_salons,
                         projections=projections,
                         african_regions=AFRICAN_REGIONS,
                         continental_plans=CONTINENTAL_PLANS)

@superadmin_bp.route('/continental-pricing')
@login_required
@roles_required('superadmin')
def continental_pricing():
    """View all continental pricing plans"""
    
    all_plans = ContinentalSubscriptionManager.get_all_regional_plans()
    
    return render_template('superadmin/continental_picing.html',
                         all_plans=all_plans,
                         regions=AFRICAN_REGIONS,
                         plans=CONTINENTAL_PLANS)

@superadmin_bp.route('/upgrade-salon/<int:salon_id>', methods=['GET', 'POST'])
@login_required
@roles_required('superadmin')
def upgrade_salon_continental(salon_id):
    """Upgrade salon to continental plan"""
    
    salon = Salon.query.get_or_404(salon_id)
    
    if request.method == 'POST':
        plan = request.form.get('plan')
        region = request.form.get('region')
        
        try:
            # Update salon region
            salon.region = region
            salon.country = AFRICAN_REGIONS[region].countries[0]  # Default to first country in region
            salon.data_residency_location = salon.country
            
            # Upgrade to continental plan
            salon.upgrade_to_continental_plan(plan)
            
            db.session.commit()
            flash(f'Salon {salon.name} upgraded to {plan} plan in {AFRICAN_REGIONS[region].name}', 'success')
            return redirect(url_for('superadmin.salon_detail', id=salon_id))
            
        except Exception as e:
            flash(f'Error upgrading salon: {str(e)}', 'error')
    
    # Get current pricing info
    current_pricing = salon.get_regional_pricing_info()
    
    return render_template('superadmin/upgrade_salon.html',
                         salon=salon,
                         current_pricing=current_pricing,
                         regions=AFRICAN_REGIONS,
                         plans=CONTINENTAL_PLANS)

@superadmin_bp.route('/api/continental-stats')
@login_required
@roles_required('superadmin')
def api_continental_stats():
    """API endpoint for continental statistics"""
    
    stats = {
        'total_salons': Salon.query.count(),
        'active_salons': Salon.query.filter_by(is_active=True).count(),
        'regional_breakdown': {},
        'plan_distribution': {},
        'currency_distribution': {}
    }
    
    # Regional breakdown
    for region_key in AFRICAN_REGIONS:
        salons = Salon.query.filter_by(region=region_key).all()
        stats['regional_breakdown'][region_key] = {
            'count': len(salons),
            'active': len([s for s in salons if s.is_active])
        }
    
    # No plan distribution - all salons on same plan
    stats['plan_distribution'] = {'standard': Salon.query.filter_by(is_active=True).count()}
    
    # Currency distribution
    for region_key, region_config in AFRICAN_REGIONS.items():
        count = Salon.query.filter_by(region=region_key).count()
        if count > 0:
            stats['currency_distribution'][region_config.currency] = count
    
    return jsonify(stats)

@superadmin_bp.route('/api/currency-converter')
@login_required
@roles_required('superadmin')
def api_currency_converter():
    """Convert amounts between currencies"""
    
    amount = float(request.args.get('amount', 0))
    from_currency = request.args.get('from_currency', 'KES')
    to_currency = request.args.get('to_currency', 'KES')
    
    try:
        # Convert to KES first (base currency)
        if from_currency != 'KES':
            amount_kes = amount / CurrencyConverter.EXCHANGE_RATES[from_currency]
        else:
            amount_kes = amount
        
        # Convert from KES to target currency
        if to_currency != 'KES':
            converted_amount = amount_kes * CurrencyConverter.EXCHANGE_RATES[to_currency]
        else:
            converted_amount = amount_kes
        
        return jsonify({
            'success': True,
            'from_amount': amount,
            'from_currency': from_currency,
            'to_amount': converted_amount,
            'to_currency': to_currency,
            'formatted_from': CurrencyConverter.format_currency(amount, from_currency),
            'formatted_to': CurrencyConverter.format_currency(converted_amount, to_currency)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@superadmin_bp.route('/resource-calculator')
@login_required
@roles_required('superadmin')
def resource_calculator():
    """Continental resource calculator"""
    
    target_salons = int(request.args.get('salons', 1000))
    resources = estimate_continental_resources(target_salons)
    
    return render_template('superadmin/resource_calculator.html',
                         target_salons=target_salons,
                         resources=resources)

@superadmin_bp.route('/compliance-dashboard')
@login_required
@roles_required('superadmin')
def compliance_dashboard():
    """Regional compliance dashboard"""
    
    from app.continental_scaling import ComplianceManager, COMPLIANCE_REQUIREMENTS
    
    # Get compliance status by country
    compliance_by_country = {}
    
    for salon in Salon.query.all():
        country = salon.country or 'KE'
        if country not in compliance_by_country:
            compliance_by_country[country] = {
                'salon_count': 0,
                'compliance_frameworks': ComplianceManager.get_compliance_for_country(country),
                'data_residency_compliant': ComplianceManager.is_data_residency_compliant(
                    country, salon.data_residency_location or 'KE'
                )
            }
        
        compliance_by_country[country]['salon_count'] += 1
    
    return render_template('superadmin/compliance_dashboard.html',
                         compliance_by_country=compliance_by_country,
                         compliance_requirements=COMPLIANCE_REQUIREMENTS)
