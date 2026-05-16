"""Billing domain models - BillingRecord, PricingConfig, PricingHistory, PaymentConfig, ContactConfig."""
from datetime import datetime, timezone
from app import db


# Helper for UTC time to ensure Python 3.12 compatibility
def get_utc_now():
    return datetime.now(timezone.utc)


class BillingRecord(db.Model):
    """Tenant-isolated billing records for subscription payments"""
    __tablename__ = 'billing_records'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    
    # Tenant isolation
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False, index=True)
    
    # Billing details
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')
    branches_count = db.Column(db.Integer, default=1)
    
    # Payment information
    payment_method = db.Column(db.String(50), default='google_pay')
    payment_status = db.Column(db.String(20), default='completed')  # pending, completed, failed, refunded
    payment_date = db.Column(db.DateTime, default=get_utc_now)
    
    # Billing period
    billing_period_start = db.Column(db.Date, nullable=False)
    billing_period_end = db.Column(db.Date, nullable=False)
    
    # Additional details
    description = db.Column(db.Text)
    payment_metadata = db.Column(db.JSON)  # Store additional payment details
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    
    # Relationships
    salon = db.relationship('Salon', backref='billing_records')
    created_by = db.relationship('Worker', foreign_keys=[created_by_id])
    
    def __repr__(self):
        return f'<BillingRecord {self.transaction_id}>'

class PricingConfig(db.Model):
    """Dynamic pricing configuration managed by superadmin"""
    __tablename__ = 'pricing_config'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Pricing settings
    price_per_branch_usd = db.Column(db.Float, nullable=False, default=30.0)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    
    # Regional pricing multipliers
    east_africa_multiplier = db.Column(db.Float, nullable=False, default=120.0)  # KES conversion
    west_africa_multiplier = db.Column(db.Float, nullable=False, default=780.0)  # NGN conversion  
    southern_africa_multiplier = db.Column(db.Float, nullable=False, default=18.5)  # ZAR conversion
    north_africa_multiplier = db.Column(db.Float, nullable=False, default=48.0)   # EGP conversion
    central_africa_multiplier = db.Column(db.Float, nullable=False, default=552.0) # XAF conversion
    
    # Enterprise pricing (for 50+ branches)
    enterprise_price_per_branch_usd = db.Column(db.Float, nullable=False, default=25.0)
    enterprise_min_branches = db.Column(db.Integer, nullable=False, default=50)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    updated_by = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=True)
    
    # Status
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    
    def __repr__(self):
        return f'<PricingConfig ${self.price_per_branch_usd}/branch>'
    
    @classmethod
    def get_active_config(cls):
        """Get the currently active pricing configuration"""
        return cls.query.filter_by(is_active=True).first()
    
    def get_price_for_region(self, region_code):
        """Get price per branch for a specific region"""
        multipliers = {
            'east_africa': self.east_africa_multiplier,
            'west_africa': self.west_africa_multiplier,
            'southern_africa': self.southern_africa_multiplier,
            'north_africa': self.north_africa_multiplier,
            'central_africa': self.central_africa_multiplier
        }
        
        multiplier = multipliers.get(region_code, self.east_africa_multiplier)
        return self.price_per_branch_usd * multiplier
    
    def get_enterprise_price_for_region(self, region_code):
        """Get enterprise price per branch for a specific region"""
        multipliers = {
            'east_africa': self.east_africa_multiplier,
            'west_africa': self.west_africa_multiplier,
            'southern_africa': self.southern_africa_multiplier,
            'north_africa': self.north_africa_multiplier,
            'central_africa': self.central_africa_multiplier
        }
        
        multiplier = multipliers.get(region_code, self.east_africa_multiplier)
        return self.enterprise_price_per_branch_usd * multiplier
    
    def calculate_monthly_cost(self, branch_count, region_code='east_africa', is_enterprise=False):
        """Calculate monthly cost for given branch count and region"""
        if is_enterprise and branch_count >= self.enterprise_min_branches:
            price_per_branch = self.get_enterprise_price_for_region(region_code)
        else:
            price_per_branch = self.get_price_for_region(region_code)
        
        return branch_count * price_per_branch

class PricingHistory(db.Model):
    """History of pricing changes for audit trail"""
    __tablename__ = 'pricing_history'
    
    id = db.Column(db.Integer, primary_key=True)
    pricing_config_id = db.Column(db.Integer, db.ForeignKey('pricing_config.id'), nullable=False)
    
    # Old values
    old_price_per_branch = db.Column(db.Float, nullable=True)
    old_enterprise_price = db.Column(db.Float, nullable=True)
    
    # New values  
    new_price_per_branch = db.Column(db.Float, nullable=False)
    new_enterprise_price = db.Column(db.Float, nullable=True)
    
    # Change details
    change_reason = db.Column(db.Text, nullable=True)
    changed_by = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    changed_at = db.Column(db.DateTime, default=get_utc_now)
    
    # Metadata
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<PricingHistory ${self.old_price_per_branch} -> ${self.new_price_per_branch}>'

class PaymentConfig(db.Model):
    """Payment gateway configuration managed by superadmin"""
    __tablename__ = 'payment_config'

    id = db.Column(db.Integer, primary_key=True)

    # Google Pay Settings
    google_pay_merchant_id = db.Column(db.String(255), nullable=True)
    google_pay_merchant_name = db.Column(db.String(255), nullable=True, default='Africa SPA System')
    google_pay_environment = db.Column(db.String(20), nullable=True, default='TEST')  # TEST or PRODUCTION

    # Stripe Settings (for card payments)
    stripe_publishable_key = db.Column(db.String(255), nullable=True)
    stripe_secret_key = db.Column(db.String(255), nullable=True)
    stripe_webhook_secret = db.Column(db.String(255), nullable=True)

    # PayPal Settings
    paypal_client_id = db.Column(db.String(255), nullable=True)
    paypal_client_secret = db.Column(db.String(255), nullable=True)
    paypal_environment = db.Column(db.String(20), nullable=True, default='sandbox')  # sandbox or live

    # Flutterwave Settings (for African payments)
    flutterwave_public_key = db.Column(db.String(255), nullable=True)
    flutterwave_secret_key = db.Column(db.String(255), nullable=True)
    flutterwave_encryption_key = db.Column(db.String(255), nullable=True)

    # M-Pesa Settings (for Kenya)
    mpesa_consumer_key = db.Column(db.String(255), nullable=True)
    mpesa_consumer_secret = db.Column(db.String(255), nullable=True)
    mpesa_shortcode = db.Column(db.String(20), nullable=True)
    mpesa_passkey = db.Column(db.String(255), nullable=True)

    # General Settings
    default_currency = db.Column(db.String(3), nullable=True, default='USD')
    enable_test_mode = db.Column(db.Boolean, default=True)

    # Metadata
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    updated_by = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=True)

    # Status
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f'<PaymentConfig {self.google_pay_merchant_name}>'

    @classmethod
    def get_active_config(cls):
        """Get the currently active payment configuration"""
        return cls.query.filter_by(is_active=True).first()

    def get_masked_secret(self, field_name):
        """Get masked version of secret for display"""
        value = getattr(self, field_name, '')
        if not value:
            return ''
        if len(value) <= 8:
            return '*' * len(value)
        return value[:4] + '*' * (len(value) - 8) + value[-4:]

class ContactConfig(db.Model):
    """Contact information configuration managed by superadmin"""
    __tablename__ = 'contact_config'

    id = db.Column(db.Integer, primary_key=True)

    # Support Email Addresses
    support_email = db.Column(db.String(255), nullable=True, default='support@africspa.com')
    billing_email = db.Column(db.String(255), nullable=True, default='billing@africspa.com')
    sales_email = db.Column(db.String(255), nullable=True, default='sales@africspa.com')
    technical_email = db.Column(db.String(255), nullable=True, default='tech@africspa.com')

    # Phone Numbers
    support_phone = db.Column(db.String(50), nullable=True)
    sales_phone = db.Column(db.String(50), nullable=True)
    whatsapp_number = db.Column(db.String(50), nullable=True)

    # Physical Address
    company_name = db.Column(db.String(255), nullable=True, default='Africa SPA System')
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)

    # Social Media Links
    website_url = db.Column(db.String(255), nullable=True, default='https://africspa.com')
    facebook_url = db.Column(db.String(255), nullable=True)
    twitter_url = db.Column(db.String(255), nullable=True)
    instagram_url = db.Column(db.String(255), nullable=True)
    linkedin_url = db.Column(db.String(255), nullable=True)

    # Business Hours
    business_hours = db.Column(db.Text, nullable=True, default='Mon-Fri: 8:00 AM - 6:00 PM\nSat: 9:00 AM - 4:00 PM\nSun: Closed')

    # Metadata
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    updated_by = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=True)

    # Status
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f'<ContactConfig {self.company_name}>'

    @classmethod
    def get_active_config(cls):
        """Get the currently active contact configuration"""
        return cls.query.filter_by(is_active=True).first()
