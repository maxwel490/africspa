"""Tenancy domain models - Salon and Branch."""
from datetime import datetime, timezone, timedelta
from app import db


# Helper for UTC time to ensure Python 3.12 compatibility
def get_utc_now():
    return datetime.now(timezone.utc)


class Salon(db.Model):
    """Salon/Tenant model for multi-tenant SaaS architecture"""
    __tablename__ = 'salons'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    logo_url = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    subscription_expires = db.Column(db.DateTime)
    max_branches = db.Column(db.Integer, default=3)
    max_staff = db.Column(db.Integer, default=10)
    max_clients = db.Column(db.Integer, default=500)  # Added for client limits
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # Billing and subscription fields
    billing_email = db.Column(db.String(100))
    billing_phone = db.Column(db.String(20))
    billing_address = db.Column(db.Text)
    payment_method = db.Column(db.String(50))  # mpesa, card, bank
    last_payment_date = db.Column(db.DateTime)
    next_billing_date = db.Column(db.DateTime)
    
    # Configuration fields
    timezone = db.Column(db.String(50), default='Africa/Nairobi')
    currency = db.Column(db.String(10), default='KES')
    country = db.Column(db.String(50), default='Kenya')
    
    # Feature toggles
    enable_service_rectification = db.Column(db.Boolean, default=True)
    
    # Features flags
    feature_appointments = db.Column(db.Boolean, default=True)
    feature_inventory = db.Column(db.Boolean, default=True)
    feature_reporting = db.Column(db.Boolean, default=True)
    feature_api_access = db.Column(db.Boolean, default=False)
    feature_custom_branding = db.Column(db.Boolean, default=False)
    feature_multi_branch = db.Column(db.Boolean, default=True)
    
    # Business model fields
    has_internal_shop = db.Column(db.Boolean, default=False)  # Whether salon runs internal product shop
    shop_commission_rate = db.Column(db.Float, default=0.0)  # Commission rate for internal shop sales
    
    # Payment configuration
    payment_config = db.Column(db.Text)  # JSON configuration for payment methods
    has_backbar = db.Column(db.Boolean, default=True)  # Whether salon uses backbar deductions
    
    # Relationships
    branches = db.relationship('Branch', backref='salon', lazy=True, cascade='all, delete-orphan')
    workers = db.relationship('Worker', backref='salon', lazy=True, cascade='all, delete-orphan')
    clients = db.relationship('Client', backref='salon', lazy=True, cascade='all, delete-orphan')
    service_orders = db.relationship('ServiceOrder', backref='salon', lazy=True, cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', backref='salon', lazy=True, cascade='all, delete-orphan')
    products = db.relationship('Product', backref='salon', lazy=True, cascade='all, delete-orphan')
    services = db.relationship('Service', backref='salon', lazy=True, cascade='all, delete-orphan')
    expenses = db.relationship('Expense', backref='salon', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Salon {self.name}>'
    
    def get_subscription_price(self):
        """Get monthly price using dynamic pricing configuration"""
        from app.domains.billing.models.billing_models import PricingConfig
        # Count active branches
        branch_count = len([b for b in self.branches if b.is_active]) if self.branches else 1
        
        # Get dynamic pricing from database
        try:
            pricing_config = PricingConfig.get_active_config()
            if pricing_config:
                # Check if this salon qualifies for enterprise pricing
                is_enterprise = branch_count >= pricing_config.enterprise_min_branches
                
                # Get region from country or default to East Africa
                region = getattr(self, 'region', 'east_africa') or 'east_africa'
                
                if is_enterprise:
                    return pricing_config.calculate_monthly_cost(branch_count, region, is_enterprise=True)
                else:
                    return pricing_config.calculate_monthly_cost(branch_count, region)
        except:
            pass
        
        # Fallback to $30 USD per branch in KES
        return branch_count * 30 * 120  # $30 * 120 KES/USD
    
    def get_regional_pricing_info(self):
        """Get complete regional pricing information"""
        from app.continental_scaling import ContinentalSubscriptionManager
        region = getattr(self, 'region', 'east_africa') or 'east_africa'
        branch_count = len([b for b in self.branches if b.is_active]) if self.branches else 1
        
        try:
            region_config = ContinentalSubscriptionManager.AFRICAN_REGIONS.get(region)
            if region_config:
                price_per_branch_usd = 30
                total_price_usd = price_per_branch_usd * branch_count
                total_price_local = total_price_usd * region_config.base_multiplier * 120
                
                return {
                    'salon_name': self.name,
                    'region': region_config.name,
                    'currency': 'KES' if region_config.currency == 'KES' else region_config.currency,
                    'price_per_branch_usd': price_per_branch_usd,
                    'total_price_usd': total_price_usd,
                    'total_price_local': total_price_local,
                    'unlimited_workers_clients': True
                }
        except Exception as e:
            return {
                'salon_name': self.name,
                'error': str(e),
                'fallback_price': branch_count * 30  # $30 per branch fallback
            }
    
    def get_monthly_cost_breakdown(self):
        """Get detailed monthly cost breakdown"""
        from .continental_scaling import ContinentalSubscriptionManager
        
        return ContinentalSubscriptionManager.calculate_salon_monthly_cost(self)
    
    def upgrade_to_continental_plan(self, plan):
        """Upgrade to continental subscription plan"""
        from .continental_scaling import ContinentalSubscriptionManager
        
        return ContinentalSubscriptionManager.upgrade_salon_limits(self, plan)
    
    def is_subscription_active(self):
        """Check if subscription is active and not expired"""
        if not self.is_active:
            return False
        if self.subscription_expires and self.subscription_expires < datetime.utcnow():
            return False
        return True
    
    def get_usage_stats(self):
        """Get current usage statistics for this salon"""
        return {
            'branches_used': len([b for b in self.branches if b.is_active]),
            'staff_used': len([w for w in self.workers if w.is_active]),
            'clients_count': len(self.clients),
            'branches_limit': self.max_branches,
            'staff_limit': self.max_staff,
            'clients_limit': self.max_clients
        }

class Branch(db.Model):
    """Salon branches with multi-tenant support"""
    __tablename__ = 'branches'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, index=True)
    code = db.Column(db.String(10), unique=True, nullable=False)  # Branch code for internal use
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # Multi-tenant relationship
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=True)  # Nullable for superadmin
    
    # Location and contact
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    manager_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    # Operating hours
    opening_time = db.Column(db.String(20))  # HH:MM format
    closing_time = db.Column(db.String(20))  # HH:MM format
    days_open = db.Column(db.String(20))  # Comma-separated days
    
    # Configuration
    timezone = db.Column(db.String(50))
    currency = db.Column(db.String(10), default='KES')
    
    # Relationships
    manager = db.relationship('Worker', foreign_keys=[manager_id], backref='managed_branches')
    
    # Note: Use direct queries for relationships due to SQLAlchemy compatibility
    # Example: Worker.query.filter_by(branch=branch_name, salon_id=salon_id)
    
    def __repr__(self):
        return f'<Branch {self.name}>'
