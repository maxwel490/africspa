# --- ULTIMATE MULTI-TENANT SALON MANAGEMENT SYSTEM ---
# Consolidated from all model files with complete SaaS features

from datetime import datetime, timezone, timedelta
from . import db, login_manager 
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

# Helper for UTC time to ensure Python 3.12 compatibility
def get_utc_now():
    return datetime.now(timezone.utc)

# --- SALON/TENANT MODEL ---

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

# --- STAFF & AUTHENTICATION ---

class Worker(db.Model, UserMixin):
    """Internal Staff: Super Admin, Admin, Accountant, Salonist"""
    __tablename__ = 'workers'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.String(255))
    id_number = db.Column(db.String(50), unique=True, index=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)  # superadmin, admin, accountant, salonist
    
    # Multi-tenant fields
    branch = db.Column(db.String(20), index=True) 
    specialty = db.Column(db.String(50))
    base_salary = db.Column(db.Float, default=0.0)
    commission_rate = db.Column(db.Float, default=0.0)  # Custom commission rate
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    last_login = db.Column(db.DateTime)
    
    # Multi-tenant relationship
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=True)  # Nullable for superadmin
    
    # Audit fields
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id', name='fk_worker_creator'), nullable=True)
    profile_image = db.Column(db.String(255))
    bio = db.Column(db.Text)
    
    # Permissions and settings
    permissions = db.Column(db.Text)  # JSON string for custom permissions
    preferences = db.Column(db.Text)   # JSON string for user preferences
    language = db.Column(db.String(10), default='en')
    
    # Password security fields
    password_changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    password_history = db.Column(db.Text)  # JSON string of password hashes
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime)
    is_locked = db.Column(db.Boolean, default=False)
    locked_until = db.Column(db.DateTime)
    password_expired = db.Column(db.Boolean, default=False)
    
    # Relationships - simplified to avoid SQLAlchemy ambiguity
    # Use direct queries for appointments, inventory, and created workers
    # Example: Appointment.query.filter_by(worker_id=self.id, salon_id=self.salon_id)
    
    def set_password(self, password):
        from app.security.password_policy import password_policy
        import json
        
        # Validate password against policy
        validation = password_policy.validate_password(password, self.username, self.email)
        if not validation['valid']:
            raise ValueError(f"Password validation failed: {'; '.join(validation['errors'])}")
        
        # Store old password in history
        if self.password_hash:
            import hashlib
            if not self.password_history:
                self.password_history = json.dumps([])
            
            history = json.loads(self.password_history)
            history.append({
                'hash': hashlib.sha256(self.password_hash.encode()).hexdigest(),
                'changed_at': datetime.utcnow().isoformat()
            })
            
            # Keep only last N passwords
            if len(history) > password_policy.password_history:
                history = history[-password_policy.password_history:]
            
            self.password_history = json.dumps(history)
        
        # Set new password
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.utcnow()
        self.password_expired = False
        self.failed_login_attempts = 0
        self.is_locked = False
        self.locked_until = None

    def check_password(self, password):
        from app.security.password_policy import password_policy
        
        # Check if account is locked
        if self.is_locked and self.locked_until and datetime.utcnow() < self.locked_until:
            return False
        
        # Check password
        if not check_password_hash(self.password_hash, password):
            self._record_failed_login()
            return False
        
        # Reset failed attempts on successful login
        if self.failed_login_attempts > 0:
            self.failed_login_attempts = 0
            self.last_failed_login = None
            self.is_locked = False
            self.locked_until = None
        
        # Check if password is expired
        if password_policy.is_password_expired(self.password_changed_at):
            self.password_expired = True
        
        return True

    def _record_failed_login(self):
        """Record failed login attempt"""
        from app.security.password_policy import password_policy
        
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.utcnow()
        
        # Lock account after too many failed attempts
        max_attempts = current_app.config.get('MAX_LOGIN_ATTEMPTS', 5)
        if self.failed_login_attempts >= max_attempts:
            lockout_minutes = current_app.config.get('ACCOUNT_LOCKOUT_MINUTES', 30)
            self.is_locked = True
            self.locked_until = datetime.utcnow() + timedelta(minutes=lockout_minutes)

    def is_account_locked(self) -> bool:
        """Check if account is currently locked"""
        if not self.is_locked:
            return False
        
        if self.locked_until and datetime.utcnow() > self.locked_until:
            # Lockout period has expired
            self.is_locked = False
            self.locked_until = None
            self.failed_login_attempts = 0
            return False
        
        return True

    def get_password_strength(self, password: str) -> dict:
        """Get password strength for a given password"""
        from app.security.password_policy import password_policy
        return password_policy.validate_password(password, self.username, self.email)

    def get_password_requirements(self) -> dict:
        """Get password requirements"""
        from app.security.password_policy import password_policy
        return password_policy.get_password_requirements()

    def get_last_recorded_work_time(self):
        """Return the latest appointment timestamp for this worker, if any."""
        return db.session.query(func.max(Appointment.appointment_time)).filter(
            Appointment.worker_id == self.id
        ).scalar()

    @staticmethod
    def _to_naive_utc(value):
        if not value:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def is_inactive_for_no_work(self, days_without_work=14, reference_time=None):
        """Flag workers with no recent appointments for the configured threshold."""
        now_value = self._to_naive_utc(reference_time) or datetime.utcnow()
        threshold_time = now_value - timedelta(days=days_without_work)
        last_work_at = self._to_naive_utc(self.get_last_recorded_work_time())

        if last_work_at:
            return last_work_at < threshold_time

        # If never worked, consider account age to avoid marking new hires inactive immediately.
        created_at = self._to_naive_utc(self.created_at) or now_value
        return created_at < threshold_time

    def has_permission(self, permission):
        """Check if worker has specific permission"""
        if not self.permissions:
            return False
        import json
        perms = json.loads(self.permissions)
        return permission in perms
    
    def get_full_name(self):
        """Get formatted full name"""
        return self.full_name.strip()
    
    def __repr__(self):
        return f'<Worker {self.username}>'

# --- BRANCHES ---

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

# --- CLIENTS & SERVICES ---

class Client(db.Model):
    """Multi-tenant client management"""
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))  # Email uniqueness enforced at salon level
    phone = db.Column(db.String(20), index=True)
    medical_notes = db.Column(db.Text)
    
    # Multi-tenant fields
    branch = db.Column(db.String(20), nullable=False, index=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Additional fields
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    address = db.Column(db.Text)
    city = db.Column(db.String(50))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(50))
    
    # Loyalty and preferences
    loyalty_points = db.Column(db.Integer, default=0)
    membership_level = db.Column(db.String(20), default='regular')
    preferred_salonist_id = db.Column(db.Integer, db.ForeignKey('workers.id', name='fk_client_preferred_salonist'))
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    # Relationships
    appointments = db.relationship('Appointment', backref='customer', lazy=True, overlaps="client_appointments")
    preferred_salonist = db.relationship('Worker', foreign_keys=[preferred_salonist_id])
    
    def get_age(self):
        """Calculate client age"""
        if self.date_of_birth:
            today = datetime.utcnow().date()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return None
    
    def get_membership_status(self):
        """Get membership status with benefits"""
        levels = {
            'regular': {'points_multiplier': 1.0, 'discount': 0},
            'silver': {'points_multiplier': 1.2, 'discount': 5},
            'gold': {'points_multiplier': 1.5, 'discount': 10},
            'platinum': {'points_multiplier': 2.0, 'discount': 15}
        }
        return levels.get(self.membership_level, levels['regular'])
    
    def __repr__(self):
        return f'<Client {self.full_name}>'

class Service(db.Model):
    """Multi-tenant service management"""
    __tablename__ = 'services'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False) 
    category = db.Column(db.String(50), nullable=False, default='Hair', index=True)
    description = db.Column(db.Text)
    
    # Pricing
    base_price = db.Column(db.Float, nullable=False, default=0.0)
    is_fixed_base = db.Column(db.Boolean, nullable=False, default=False)
    commission_front = db.Column(db.Float, nullable=False, default=0.0)
    commission_back = db.Column(db.Float, nullable=False, default=0.0)
    
    # Duration and requirements
    duration_minutes = db.Column(db.Integer, default=60)
    preparation_time = db.Column(db.Integer, default=15)
    cleanup_time = db.Column(db.Integer, default=15)
    
    # Multi-tenant fields
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Additional fields
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    color_code = db.Column(db.String(7))  # For calendar display
    image_url = db.Column(db.String(255))
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    # Relationships
    appointments = db.relationship('Appointment', backref='service_details', lazy=True, overlaps="service_appointments")
    
    def get_commission_calculation(self, base_price_collected):
        """Calculates payouts based on service category logic."""
        if self.category == 'Hair':
            total_pool = base_price_collected * 0.5
            if 0 < self.commission_front < 1.0:
                front_payout = base_price_collected * self.commission_front
            else:
                front_payout = self.commission_front
            back_payout = max(0, total_pool - front_payout)
            return front_payout, back_payout
            
        elif self.category == 'Special Hair':
            front_payout = base_price_collected * self.commission_front
            back_payout = base_price_collected * self.commission_back
            return front_payout, back_payout
            
        else:
            front_payout = base_price_collected * self.commission_front
            return front_payout, 0.0

    def get_total_duration(self):
        """Get total service duration including prep and cleanup"""
        return self.duration_minutes + self.preparation_time + self.cleanup_time
    
    def __repr__(self):
        return f'<Service {self.name}>'

# --- CORE OPERATIONS ---

class Appointment(db.Model):
    """Multi-tenant appointment management"""
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    appointment_time = db.Column(db.DateTime, nullable=False, default=get_utc_now, index=True)
    
    # Service information
    service_id = db.Column(db.Integer, db.ForeignKey('services.id', name='fk_appointment_service_id'))
    service_type = db.Column(db.String(100), nullable=False) 
    notes = db.Column(db.Text)
    
    # Financial mapping
    transacted_total = db.Column(db.Float, default=0.0) 
    total_cost = db.Column(db.Float, default=0.0) 
    product_cost = db.Column(db.Float, default=0.0) 
    commission_earned = db.Column(db.Float, default=0.0)
    salon_cut = db.Column(db.Float, default=0.0)
    salon_surplus = db.Column(db.Float, default=0.0)
    
    # Payment and status
    payment_method = db.Column(db.String(50))
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, refunded
    receipt_no = db.Column(db.String(50), index=True)
    is_model = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='Scheduled', index=True)  # Scheduled, In Progress, Completed, Cancelled, No Show
    
    # Multi-tenant fields
    branch = db.Column(db.String(20), nullable=False, index=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Client and staff
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', name='fk_appointment_client'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id', name='fk_appointment_worker'), nullable=False)
    
    # Additional fields
    department = db.Column(db.String(50))
    duration_actual = db.Column(db.Integer)  # Actual duration
    tips = db.Column(db.Float, default=0.0)
    rating = db.Column(db.Integer)  # 1-5 stars
    feedback = db.Column(db.Text)
    
    # Rectification
    parent_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    is_redo = db.Column(db.Boolean, default=False)       
    is_rectified = db.Column(db.Boolean, default=False)   
    rectification_reason = db.Column(db.Text)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id', name='fk_appointment_creator'))
    
    # Relationships
    worker = db.relationship('Worker', foreign_keys=[worker_id], backref='appointments')
    client = db.relationship('Client', foreign_keys=[client_id], backref='client_appointments', overlaps="appointments,customer")
    service = db.relationship('Service', foreign_keys=[service_id], backref='service_appointments', overlaps="appointments,service_details")
    creator = db.relationship('Worker', foreign_keys=[created_by_id], backref='created_appointments')
    
    def get_total_revenue(self):
        """Calculate total revenue including tips"""
        return self.transacted_total + (self.tips or 0.0)
    
    def get_commission_total(self):
        """Calculate total commission"""
        return self.commission_earned
    
    def get_duration_variance(self):
        """Calculate variance between scheduled and actual duration"""
        if self.duration_actual:
            return self.duration_actual - self.service.duration_minutes if self.service else 0
        return 0
    
    def __repr__(self):
        return f'<Appointment {self.id}>'

class RectificationLog(db.Model):
    """Tracks internal accounting for service redos and penalties."""
    __tablename__ = 'rectification_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    original_appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    redo_appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    
    # Financial tracking
    prep_labor_penalty = db.Column(db.Float, default=0.0) 
    material_cost_penalty = db.Column(db.Float, default=0.0)
    total_penalty = db.Column(db.Float, default=0.0)
    
    # Reason tracking
    rectification_reason = db.Column(db.Text)
    resolution_notes = db.Column(db.Text)
    
    # Staff responsibility
    undo_salonist_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    wash_salonist_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    penalized_salonist_ids = db.Column(db.String(100))  # Comma-separated IDs
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    def get_total_penalty(self):
        """Calculate total penalty amount"""
        return self.prep_labor_penalty + self.material_cost_penalty + self.total_penalty
    
    def __repr__(self):
        return f'<RectificationLog {self.id}>'

# --- INVENTORY & SUPPLIERS ---

class Product(db.Model):
    """Multi-tenant product and inventory management"""
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False)  # Stock Keeping Unit
    barcode = db.Column(db.String(50))
    description = db.Column(db.Text)
    
    # Category and classification
    category = db.Column(db.String(50), index=True) 
    subcategory = db.Column(db.String(50))
    department = db.Column(db.String(50), index=True)
    brand = db.Column(db.String(50))
    supplier = db.Column(db.String(100))
    
    # Inventory tracking
    stock_quantity = db.Column(db.Integer, default=0)
    min_stock_level = db.Column(db.Integer, default=5)
    max_stock_level = db.Column(db.Integer, default=100)
    reorder_point = db.Column(db.Integer, default=5)
    
    # Pricing
    unit_price = db.Column(db.Float, nullable=False) 
    buying_price = db.Column(db.Float, nullable=False, default=0.0)
    min_selling_price = db.Column(db.Float) 
    wholesale_price = db.Column(db.Float)
    
    # Multi-tenant fields
    branch = db.Column(db.String(20), index=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Additional fields
    unit_of_measure = db.Column(db.String(20), default='pcs')
    weight = db.Column(db.Float)
    dimensions = db.Column(db.String(50))  # LxWxH
    image_url = db.Column(db.String(255))
    
    # Status and tracking
    is_active = db.Column(db.Boolean, default=True)
    is_service = db.Column(db.Boolean, default=False)  # If true, can only be used in services
    inventory_type = db.Column(db.String(20), default='salon')  # 'salon', 'shop', 'shared'
    last_updated = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    # Relationships
    transactions = db.relationship('ProductTransaction', back_populates='product_obj', lazy=True)
    
    def get_stock_value(self):
        """Calculate total stock value"""
        return self.stock_quantity * self.unit_price
    
    def is_low_stock(self):
        """Check if product is below reorder point"""
        return self.stock_quantity <= self.reorder_point
    
    def get_profit_margin(self):
        """Calculate profit margin percentage"""
        if self.buying_price > 0:
            return ((self.unit_price - self.buying_price) / self.unit_price) * 100
        return 0
    
    def __repr__(self):
        return f'<Product {self.name}>'

class Supplier(db.Model):
    """Multi-tenant supplier management"""
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    
    # Address
    address = db.Column(db.Text)
    city = db.Column(db.String(50))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(50))
    
    # Business info
    tax_id = db.Column(db.String(50))
    payment_terms = db.Column(db.String(50))
    notes = db.Column(db.Text)
    
    # Multi-tenant fields
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    rating = db.Column(db.Integer, default=5)  # 1-5 stars
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # Relationships
    # Note: Suppliers are salon-wide resources, not tied to specific workers
    
    # Unique constraint for email within each salon
    __table_args__ = (
        db.UniqueConstraint('email', 'salon_id', name='uq_supplier_email_salon'),
    )
    
    def __repr__(self):
        return f'<Supplier {self.name} (Salon {self.salon_id})>'
    
    @staticmethod
    def validate_email_uniqueness(email, salon_id, exclude_supplier_id=None):
        """
        Validate that email is unique within the salon
        """
        if not email:
            return True
        
        query = Supplier.query.filter_by(email=email, salon_id=salon_id)
        
        if exclude_supplier_id:
            query = query.filter(Supplier.id != exclude_supplier_id)
        
        return query.first() is None
    
    def can_be_accessed_by(self, user):
        """
        Check if the current user can access this supplier
        """
        if not user.is_authenticated:
            return False
        
        # Super Admin can access all suppliers
        if user.role == 'superadmin':
            return True
        
        # Users can only access suppliers from their own salon
        return self.salon_id == user.salon_id

class SupplierInvoice(db.Model):
    """Multi-tenant supplier invoice management"""
    __tablename__ = 'supplier_invoices'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    
    # Financial details
    amount = db.Column(db.Float, nullable=False)
    tax_amount = db.Column(db.Float, default=0.0)
    discount_amount = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)
    
    # Dates
    invoice_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date)
    payment_date = db.Column(db.Date)
    
    # Status
    status = db.Column(db.String(20), default='Pending', index=True)  # Pending, Paid, Overdue, Cancelled
    payment_method = db.Column(db.String(50))
    
    # Multi-tenant fields
    branch = db.Column(db.String(50), index=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Additional fields
    currency = db.Column(db.String(10), default='KES')
    exchange_rate = db.Column(db.Float, default=1.0)
    notes = db.Column(db.Text)
    items_summary = db.Column(db.Text)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    # Relationships
    inventory_transactions = db.relationship('ProductTransaction', backref='invoice', lazy=True)
    
    def get_amount_due(self):
        """Calculate amount due after discounts"""
        return self.total_amount - self.discount_amount
    
    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.due_date and self.status != 'Paid':
            return datetime.utcnow().date() > self.due_date
        return False
    
    def __repr__(self):
        return f'<SupplierInvoice {self.invoice_number}>'

class ProductTransaction(db.Model):
    """Multi-tenant product transaction tracking"""
    __tablename__ = 'product_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_no = db.Column(db.String(50), unique=True, nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    
    # Reference documents
    invoice_id = db.Column(db.Integer, db.ForeignKey('supplier_invoices.id'))
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'))
    service_order_id = db.Column(db.Integer, db.ForeignKey('service_orders.id'))
    
    # Transaction details
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float)
    
    # Type and purpose
    transaction_type = db.Column(db.String(20), index=True)  # Restock, Sale, Transfer, Adjustment, Waste
    department = db.Column(db.String(50))
    purpose = db.Column(db.String(100))
    
    # Multi-tenant fields
    branch = db.Column(db.String(20), index=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Staff and audit
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id')) 
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    # Timestamps
    timestamp = db.Column(db.DateTime, default=get_utc_now)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # Relationships
    product_obj = db.relationship('Product', back_populates='transactions')
    appointment = db.relationship('Appointment', backref='product_usage', lazy=True)
    performed_by = db.relationship('Worker', foreign_keys=[worker_id], backref='performed_transactions')
    created_by = db.relationship('Worker', foreign_keys=[created_by_id], backref='created_transactions')
    
    def get_total_value(self):
        """Calculate total transaction value"""
        return self.quantity * self.unit_cost
    
    def __repr__(self):
        return f'<ProductTransaction {self.transaction_no}>'

# --- SERVICE ORDERS ---

class ServiceOrder(db.Model):
    """Multi-tenant service order management"""
    __tablename__ = 'service_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    # Client information
    client_name = db.Column(db.String(100), nullable=False)
    client_phone = db.Column(db.String(20), nullable=False)
    client_email = db.Column(db.String(100))
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    
    # Financial details
    subtotal = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    discount_amount = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    
    # Payment
    payment_method = db.Column(db.String(50))
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, refunded, partial
    paid_amount = db.Column(db.Float, default=0.0)
    receipt_no = db.Column(db.String(50))
    
    # Status tracking
    status = db.Column(db.String(20), default='pending', index=True)  # pending, confirmed, in_progress, completed, cancelled
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    
    # Multi-tenant fields
    branch = db.Column(db.String(20), nullable=False, index=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Additional fields
    notes = db.Column(db.Text)
    special_instructions = db.Column(db.Text)
    estimated_completion = db.Column(db.DateTime)
    actual_completion = db.Column(db.DateTime)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    completed_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    # Relationships
    created_by = db.relationship('Worker', foreign_keys=[created_by_id], backref='service_orders_created')
    completed_by = db.relationship('Worker', foreign_keys=[completed_by_id], backref='service_orders_completed')
    client = db.relationship('Client', backref='service_orders')
    services = db.relationship('ServiceOrderItem', backref='service_order', lazy=True, cascade='all, delete-orphan')
    
    def get_balance_due(self):
        """Calculate remaining balance"""
        return self.total_amount - self.paid_amount
    
    def is_overdue(self):
        """Check if order is overdue"""
        if self.estimated_completion and self.status not in ['completed', 'cancelled']:
            return datetime.utcnow() > self.estimated_completion
        return False
    
    def __repr__(self):
        return f'<ServiceOrder {self.order_number}>'

class ServiceOrderItem(db.Model):
    """Individual services within a service order"""
    __tablename__ = 'service_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    service_order_id = db.Column(db.Integer, db.ForeignKey('service_orders.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    
    # Service details
    service_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    # Commission and pricing
    commission_rate = db.Column(db.Float, default=0.0)
    commission_amount = db.Column(db.Float, default=0.0)
    discount_percentage = db.Column(db.Float, default=0.0)
    
    # Status
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, cancelled
    
    # Relationships
    service = db.relationship('Service', backref='order_items')
    
    def get_commission_value(self):
        """Calculate commission for this item"""
        return self.commission_amount or (self.total_price * self.commission_rate)
    
    def __repr__(self):
        return f'<ServiceOrderItem {self.id}>'

# --- FINANCE & RECONCILIATION ---

class Expense(db.Model):
    """Multi-tenant expense management"""
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    
    # Multi-tenant fields
    branch = db.Column(db.String(20), index=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Additional fields
    expense_date = db.Column(db.Date, nullable=False, index=True)
    month = db.Column(db.String(20), index=True)
    receipt_no = db.Column(db.String(50))
    invoice_no = db.Column(db.String(50))
    vendor = db.Column(db.String(100))
    payment_method = db.Column(db.String(50))
    
    # Approval and audit
    approved_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    approved_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    receipt_image = db.Column(db.String(255))
    
    # Status
    status = db.Column(db.String(20), default='pending', index=True)  # pending, approved, rejected
    is_reimbursable = db.Column(db.Boolean, default=True)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    # Relationships - simplified to avoid SQLAlchemy ambiguity
    # Use direct queries for approver info
    # Example: Worker.query.get(self.approved_by_id)
    
    def __repr__(self):
        return f'<Expense {self.description}>'

class BackbarGroup(db.Model):
    __tablename__ = 'backbar_groups'
    id = db.Column(db.Integer, primary_key=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Braiders", "Barbers", "Nail Technicians"
    description = db.Column(db.String(255))
    target_specialties = db.Column(db.Text)  # JSON array of specialties that belong to this group
    target_employment_types = db.Column(db.Text)  # JSON array of employment types (optional)
    is_active = db.Column(db.Boolean, default=True)
    color = db.Column(db.String(20), default='primary')  # Bootstrap color for UI
    icon = db.Column(db.String(50), default='bi-people')  # Bootstrap icon
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # Relationship
    salon = db.relationship('Salon', backref=db.backref('backbar_groups', lazy=True, cascade='all, delete-orphan'))
    
    def get_target_specialties(self):
        """Get target specialties as a list"""
        import json
        if self.target_specialties:
            try:
                return json.loads(self.target_specialties)
            except:
                return []
        return []
    
    def set_target_specialties(self, specialties_list):
        """Set target specialties from a list"""
        import json
        self.target_specialties = json.dumps(specialties_list)
    
    def get_target_employment_types(self):
        """Get target employment types as a list"""
        import json
        if self.target_employment_types:
            try:
                return json.loads(self.target_employment_types)
            except:
                return []
        return []
    
    def set_target_employment_types(self, types_list):
        """Set target employment types from a list"""
        import json
        self.target_employment_types = json.dumps(types_list)
    
    def get_eligible_workers(self, branch):
        """Get eligible workers for this group in a specific branch"""
        from app.models import Worker
        
        query = Worker.query.filter_by(branch=branch, role='salonist')
        
        # Filter by specialties if specified
        specialties = self.get_target_specialties()
        if specialties:
            query = query.filter(Worker.specialty.in_(specialties))
        
        # Filter by employment types if specified
        employment_types = self.get_target_employment_types()
        if employment_types:
            query = query.filter(Worker.employment_type.in_(employment_types))
        
        return query.all()

class StaffDeduction(db.Model):
    """Multi-tenant staff deduction management"""
    __tablename__ = 'staff_deductions'
    
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False, index=True)
    branch = db.Column(db.String(100), nullable=False, index=True)
    deduction_type = db.Column(db.String(50), nullable=False, index=True)  # advance, loan, penalty, tax, other
    amount = db.Column(db.Float, nullable=False, default=0.0)
    reason = db.Column(db.String(255))
    product_name = db.Column(db.String(100))
    target_role = db.Column(db.String(100))  # Target role for mandatory deductions
    inventory_type = db.Column(db.String(20), default='salon')  # 'salon', 'shop' - track which inventory this deduction is for
    backbar_group_id = db.Column(db.Integer, db.ForeignKey('backbar_groups.id'), nullable=True, index=True)  # Link to tenant-defined group
    week_start = db.Column(db.Date, nullable=False, index=True)  # Week start date for grouping
    month_year = db.Column(db.String(20), index=True)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    # Relationships
    worker = db.relationship('Worker', foreign_keys=[worker_id], backref='staff_deductions')
    backbar_group = db.relationship('BackbarGroup', backref=db.backref('deductions', lazy=True))
    created_by = db.relationship('Worker', foreign_keys=[created_by_id], backref='created_deductions')
    
    def get_remaining_balance(self):
        """Calculate remaining balance"""
        return self.balance_amount - self.paid_amount
    
    def is_overdue(self):
        """Check if deduction is overdue"""
        if self.next_due_date and self.status == 'active':
            return datetime.utcnow().date() > self.next_due_date
        return False
    
    def __repr__(self):
        return f'<StaffDeduction {self.id}>'

class MonthlyReconciliation(db.Model):
    """Multi-tenant monthly reconciliation"""
    __tablename__ = 'monthly_reconciliations'
    
    id = db.Column(db.Integer, primary_key=True)
    month_year = db.Column(db.String(20), nullable=False, index=True) 
    category = db.Column(db.String(20), nullable=False, index=True)   
    branch = db.Column(db.String(50), nullable=False, index=True)
    
    # Financial data
    opening_balance = db.Column(db.Float, default=0.0)
    collected_fund = db.Column(db.Float, default=0.0)
    stock_invoice_total = db.Column(db.Float, default=0.0)
    utility_share = db.Column(db.Float, default=0.0)
    other_expenses = db.Column(db.Float, default=0.0)
    staff_commissions = db.Column(db.Float, default=0.0)
    staff_deductions = db.Column(db.Float, default=0.0)
    final_diff = db.Column(db.Float, default=0.0) 
    
    # Multi-tenant fields
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Status and audit
    status = db.Column(db.String(20), default='pending', index=True)  # pending, approved, rejected
    notes = db.Column(db.Text)
    
    # Audit fields
    reconciled_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    reconciled_at = db.Column(db.DateTime, default=get_utc_now)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # Relationships
    reconciled_by = db.relationship('Worker', foreign_keys=[reconciled_by_id], backref='reconciliations')
    
    def get_expected_balance(self):
        """Calculate expected closing balance"""
        return (self.opening_balance + self.collected_fund - 
                self.stock_invoice_total - self.utility_share - self.other_expenses)
    
    def get_variance(self):
        """Calculate variance from expected"""
        expected = self.get_expected_balance()
        actual = expected - self.staff_commissions + self.staff_deductions
        return actual - self.final_diff
    
    def __repr__(self):
        return f'<MonthlyReconciliation {self.month_year} - {self.category}>'

# --- DEPARTMENT CONFIGURATION ---

class DepartmentCategoryConfig(db.Model):
    """Multi-tenant department category configuration"""
    __tablename__ = 'department_category_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    branch = db.Column(db.String(50), nullable=False, index=True)
    department = db.Column(db.String(30), nullable=False, index=True)
    categories_text = db.Column(db.String(255), default='')
    
    # Multi-tenant fields
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Audit fields
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    def get_categories(self):
        """Parse categories text into list"""
        if self.categories_text:
            return [cat.strip() for cat in self.categories_text.split(',') if cat.strip()]
        return []
    
    def set_categories(self, categories_list):
        """Set categories from list"""
        self.categories_text = ', '.join([cat.strip() for cat in categories_list if cat.strip()])
    
    def __repr__(self):
        return f'<DepartmentCategoryConfig {self.branch} - {self.department}>'

# --- SYSTEM CONFIGURATION ---

class SystemConfig(db.Model):
    """System-wide configuration settings"""
    __tablename__ = 'system_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    
    # Configuration metadata
    config_type = db.Column(db.String(50))  # string, number, boolean, json
    is_public = db.Column(db.Boolean, default=False)  # Whether config is exposed to API
    is_editable = db.Column(db.Boolean, default=True)  # Whether config can be edited by salon admins
    
    # Validation
    min_value = db.Column(db.Float)
    max_value = db.Column(db.Float)
    allowed_values = db.Column(db.Text)  # JSON string of allowed values
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    def get_parsed_value(self):
        """Parse configuration value based on type"""
        if self.config_type == 'json':
            import json
            return json.loads(self.value)
        elif self.config_type == 'number':
            return float(self.value)
        elif self.config_type == 'boolean':
            return self.value.lower() == 'true'
        else:
            return self.value
    
    def validate_value(self, new_value):
        """Validate new value against constraints"""
        if self.config_type == 'number':
            try:
                num_value = float(new_value)
                if self.min_value is not None and num_value < self.min_value:
                    return False, f"Value must be at least {self.min_value}"
                if self.max_value is not None and num_value > self.max_value:
                    return False, f"Value must be at most {self.max_value}"
                return True, "Valid"
            except ValueError:
                return False, "Invalid number format"
        
        elif self.config_type == 'boolean':
            if new_value.lower() not in ['true', 'false']:
                return False, "Must be 'true' or 'false'"
            return True, "Valid"
        
        elif self.allowed_values:
            import json
            allowed = json.loads(self.allowed_values)
            if new_value not in allowed:
                return False, f"Must be one of: {', '.join(allowed)}"
            return True, "Valid"
        
        return True, "Valid"
    
    def __repr__(self):
        return f'<SystemConfig {self.key}>'

# --- USER LOADER ---

@login_manager.user_loader
def load_user(worker_id):
    return db.session.get(Worker, int(worker_id))

# --- UTILITY FUNCTIONS ---

def get_salon_by_slug(slug):
    """Get salon by slug for subdomain routing"""
    return Salon.query.filter_by(slug=slug, is_active=True).first()

def get_user_salons(user):
    """Get all salons a user has access to"""
    if user.role == 'superadmin':
        return Salon.query.all()
    else:
        salon = Salon.query.get(user.salon_id)
        return [salon] if salon else []

def validate_subscription(salon, feature=None):
    """Validate if salon's subscription supports a feature"""
    if not salon or not salon.is_active:
        return False
    
    if salon.subscription_expires and salon.subscription_expires < datetime.utcnow():
        return False
    
    # Feature validation
    feature_map = {
        'appointments': salon.feature_appointments,
        'inventory': salon.feature_inventory,
        'reporting': salon.feature_reporting,
        'api_access': salon.feature_api_access,
        'custom_branding': salon.feature_custom_branding,
        'multi_branch': salon.feature_multi_branch
    }
    
    if feature and feature not in feature_map:
        return False
    
    return feature_map.get(feature, True) if feature else True

def calculate_total_monthly_subscription_revenue():
    """Calculate total monthly subscription revenue - $30 per branch"""
    total_revenue = 0
    
    # Calculate revenue per salon based on active branches
    salons = Salon.query.filter_by(is_active=True).all()
    for salon in salons:
        branch_count = len([b for b in salon.branches if b.is_active]) if salon.branches else 1
        total_revenue += branch_count * 30 * 120  # $30 per branch in KES
    
    return total_revenue

# --- BILLING RECORDS ---

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


# --- PRICING CONFIGURATION MODELS ---

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


# --- PAYMENT CONFIGURATION ---

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


# --- CONTACT CONFIGURATION ---

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


# --- CHAT/MESSAGING SYSTEM ---
class Message(db.Model):
    """Chat messages between users and superadmin"""
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Message content
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')  # text, image, file
    
    # Sender information
    sender_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=True)  # Nullable for public outsiders
    sender_name = db.Column(db.String(255), nullable=False)
    sender_email = db.Column(db.String(255), nullable=True)
    sender_role = db.Column(db.String(20), nullable=False)  # admin, superadmin, outsider
    
    # Recipient information
    recipient_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=True)
    recipient_name = db.Column(db.String(255), nullable=False)
    recipient_role = db.Column(db.String(20), nullable=False)
    
    # Status and metadata
    is_read = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(10), default='normal')  # low, normal, high, urgent
    
    # Session tracking for public users
    session_id = db.Column(db.String(255), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=get_utc_now)

# --- SUPPORT TICKET SYSTEM ---
class SupportTicket(db.Model):
    """Customer support tickets and sessions"""
    __tablename__ = 'support_tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Ticket information
    ticket_number = db.Column(db.String(20), unique=True, nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='open')  # open, in_progress, resolved, closed
    
    # Customer information
    customer_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    customer_name = db.Column(db.String(255), nullable=False)
    customer_email = db.Column(db.String(255), nullable=False)
    
    # Assignment and priority
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=True)
    priority = db.Column(db.String(10), default='normal')  # low, normal, high, urgent
    
    # User type classification
    user_type = db.Column(db.String(20), default='outsider')  # admin, tenant, outsider
    
    # Session tracking
    session_id = db.Column(db.String(100), unique=True, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    messages = db.relationship('Message', backref='support_ticket')
    customer = db.relationship('Client', backref='support_tickets')
    assigned_to = db.relationship('Worker', backref='assigned_tickets')
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Additional fields
    parent_message_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=True)  # For replies
    
    @classmethod
    def get_unread_count(cls, user_id, user_type='admin'):
        """Get count of unread tickets for a user"""
        return cls.query.filter_by(assigned_to_id=user_id, is_read=False).count()
    
    def __repr__(self):
        return f'<SupportTicket {self.ticket_number}>'
