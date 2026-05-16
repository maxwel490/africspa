"""
Subscription Payment Controller for Africa SPA System

Handles subscription payments using Google Pay for tenant billing.
"""

from flask import Blueprint, request, jsonify, current_app, render_template
from flask_login import login_required, current_user
from app.models import Salon, db
from app.services.subscription_payment import subscription_payment_service
from app.decorators import roles_required
import logging

logger = logging.getLogger(__name__)

subscription_payment_bp = Blueprint('subscription_payment', __name__, url_prefix='/subscription')

@subscription_payment_bp.route('/billing')
@login_required
@roles_required('admin')
def billing_dashboard():
    """Subscription billing dashboard for tenant admin"""
    try:
        if not current_user.salon_id:
            return jsonify({'error': 'No salon associated with user'}), 400
        
        # Get subscription status
        subscription_status = subscription_payment_service.get_subscription_status(current_user.salon_id)
        
        # Get billing history
        billing_history = subscription_payment_service.get_billing_history(current_user.salon_id)
        
        return render_template('subscription/billing.html',
                             subscription=subscription_status,
                             billing_history=billing_history)
        
    except Exception as e:
        logger.error(f"Error loading billing dashboard: {str(e)}")
        return jsonify({'error': 'Failed to load billing dashboard'}), 500

@subscription_payment_bp.route('/google-pay/config')
@login_required
@roles_required('admin')
def get_google_pay_config():
    """Get Google Pay configuration for subscription payment"""
    try:
        if not current_user.salon_id:
            return jsonify({'error': 'No salon associated with user'}), 400
        
        config = subscription_payment_service.get_google_pay_config(current_user.salon_id)
        return jsonify(config)
        
    except Exception as e:
        logger.error(f"Error getting Google Pay config: {str(e)}")
        return jsonify({'error': 'Failed to get payment configuration'}), 500

@subscription_payment_bp.route('/google-pay/process', methods=['POST'])
@login_required
@roles_required('admin')
def process_subscription_payment():
    """Process subscription payment using Google Pay"""
    try:
        data = request.get_json()
        
        if not current_user.salon_id:
            return jsonify({'error': 'No salon associated with user'}), 400
        
        # Validate required fields
        if 'paymentToken' not in data:
            return jsonify({'error': 'Payment token is required'}), 400
        
        # Process payment
        success, transaction_id, response = subscription_payment_service.process_subscription_payment(
            salon_id=current_user.salon_id,
            payment_token=data['paymentToken'],
            user_id=current_user.id
        )
        
        if success:
            return jsonify({
                'success': True,
                'transaction_id': transaction_id,
                'message': 'Subscription payment processed successfully',
                'details': response
            })
        else:
            return jsonify({
                'success': False,
                'error': response.get('error', 'Payment processing failed')
            }), 400
            
    except Exception as e:
        logger.error(f"Error processing subscription payment: {str(e)}")
        return jsonify({'error': 'Payment processing failed'}), 500

@subscription_payment_bp.route('/status')
@login_required
@roles_required('admin')
def get_subscription_status():
    """Get current subscription status"""
    try:
        if not current_user.salon_id:
            return jsonify({'error': 'No salon associated with user'}), 400
        
        status = subscription_payment_service.get_subscription_status(current_user.salon_id)
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting subscription status: {str(e)}")
        return jsonify({'error': 'Failed to get subscription status'}), 500

@subscription_payment_bp.route('/history')
@login_required
@roles_required('admin')
def get_billing_history():
    """Get billing history"""
    try:
        if not current_user.salon_id:
            return jsonify({'error': 'No salon associated with user'}), 400
        
        limit = request.args.get('limit', 10, type=int)
        history = subscription_payment_service.get_billing_history(current_user.salon_id, limit)
        
        return jsonify({
            'history': history,
            'total': len(history)
        })
        
    except Exception as e:
        logger.error(f"Error getting billing history: {str(e)}")
        return jsonify({'error': 'Failed to get billing history'}), 500

@subscription_payment_bp.route('/calculate')
@login_required
@roles_required('admin')
def calculate_subscription():
    """Calculate current subscription cost"""
    try:
        if not current_user.salon_id:
            return jsonify({'error': 'No salon associated with user'}), 400
        
        subscription = subscription_payment_service.calculate_monthly_subscription(current_user.salon_id)
        return jsonify(subscription)
        
    except Exception as e:
        logger.error(f"Error calculating subscription: {str(e)}")
        return jsonify({'error': 'Failed to calculate subscription'}), 500
