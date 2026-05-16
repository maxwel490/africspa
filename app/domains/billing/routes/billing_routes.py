"""
Billing domain routes.

Handles subscription payments, pricing management, payment settings, and billing records.

Currently served by:
- subscription_payment_bp: billing_dashboard, get_google_pay_config,
                          process_subscription_payment, get_subscription_status,
                          get_billing_history, calculate_subscription
- superadmin_pricing_bp: pricing management
- superadmin_bp: payment_settings, contact_settings
- admin_bp: payment_settings

The subscription_payment and pricing_management routes have been copied to this domain.
Other billing routes will be migrated incrementally.
"""
from flask import Blueprint

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')
