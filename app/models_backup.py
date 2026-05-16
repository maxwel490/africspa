# --- MULTI-TENANT SALON MANAGEMENT SYSTEM ---

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
    """Salon/Tenant model for multi-tenant architecture"""
    __tablename__ = 'salons'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    logo_url = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    subscription_plan = db.Column(db.String(20), default='basic')  # basic, professional, enterprise
    subscription_expires = db.Column(db.DateTime)
    max_branches = db.Column(db.Integer, default=3)
    max_staff = db.Column(db.Integer, default=10)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # Relationships
    branches = db.relationship('Branch', backref='salon', lazy=True, cascade='all, delete-orphan')
    workers = db.relationship('Worker', backref='salon', lazy=True, cascade='all, delete-orphan')
    clients = db.relationship('Client', backref='salon', lazy=True, cascade='all, delete-orphan')
    service_orders = db.relationship('ServiceOrder', backref='salon', lazy=True, cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', backref='salon', lazy=True, cascade='all, delete-orphan')
    products = db.relationship('Product', backref='salon', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Salon {self.name}>'

# --- STAFF & AUTHENTICATION ---

class Worker(db.Model, UserMixin):
    """Internal Staff: Admin, Accountant, Salonist"""
    __tablename__ = 'workers'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    id_number = db.Column(db.String(50))
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True) # admin, accountant, salonist
    branch = db.Column(db.String(20), index=True) 
    specialty = db.Column(db.String(50))
    base_salary = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # Audit: Who created this staff member
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id', name='fk_worker_creator'), nullable=True)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Relationships
    appointments = db.relationship('Appointment', back_populates='worker', lazy=True)
    inventory_actions = db.relationship('ProductTransaction', backref='performed_by', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

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

# --- BRANCHES ---

class Branch(db.Model):
    __tablename__ = 'branches'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Note: Use direct queries for relationships due to SQLAlchemy compatibility
    # Example: Worker.query.filter_by(branch=branch_name, salon_id=salon_id)

# --- CLIENTS & SERVICES ---

class Client(db.Model):
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True)
    phone = db.Column(db.String(20), index=True)
    medical_notes = db.Column(db.Text)
    branch = db.Column(db.String(20), nullable=False, index=True)
    preferred_salonist_id = db.Column(db.Integer, db.ForeignKey('workers.id', name='fk_client_preferred_salonist'))
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    appointments = db.relationship('Appointment', backref='customer', lazy=True)

class Service(db.Model):
    __tablename__ = 'services'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False) 
    category = db.Column(db.String(50), nullable=False, default='Hair', index=True)
    base_price = db.Column(db.Float, nullable=False, default=0.0)
    is_fixed_base = db.Column(db.Boolean, nullable=False, default=False)
    commission_front = db.Column(db.Float, nullable=False, default=0.0)
    commission_back = db.Column(db.Float, nullable=False, default=0.0) 
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    appointments = db.relationship('Appointment', backref='service_details', lazy=True)

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

# --- CORE OPERATIONS ---

class Appointment(db.Model):
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    appointment_time = db.Column(db.DateTime, nullable=False, default=get_utc_now, index=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id', name='fk_appointment_service_id'))
    service_type = db.Column(db.String(100), nullable=False) 
    
    # Financial Mapping
    transacted_total = db.Column(db.Float, default=0.0) 
    total_cost = db.Column(db.Float, default=0.0) 
    product_cost = db.Column(db.Float, default=0.0) 
    commission_earned = db.Column(db.Float, default=0.0)
    salon_cut = db.Column(db.Float, default=0.0) # Added to match DB
    salon_surplus = db.Column(db.Float, default=0.0)
    
    payment_method = db.Column(db.String(50))
    receipt_no = db.Column(db.String(50), index=True)
    is_model = db.Column(db.Boolean, default=False)
    
    # Rectification / Redo Logic
    parent_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    is_redo = db.Column(db.Boolean, default=False)       
    is_rectified = db.Column(db.Boolean, default=False)   
    
    is_payer = db.Column(db.Boolean, default=True) 
    branch = db.Column(db.String(20), nullable=False, index=True)
    department = db.Column(db.String(50)) # Added to match DB
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', name='fk_appointment_client'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id', name='fk_appointment_worker'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Relationships
    worker = db.relationship('Worker', back_populates='appointments')
    status = db.Column(db.String(20), default='Completed', index=True) 
    notes = db.Column(db.Text)
    tips = db.Column(db.Float, default=0.0)
    
    rectification_details = db.relationship('RectificationLog', 
                                            foreign_keys='RectificationLog.redo_appointment_id', 
                                            uselist=False)

class RectificationLog(db.Model):
    """Tracks internal accounting for service redos and penalties."""
    __tablename__ = 'rectification_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    original_appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    redo_appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    
    prep_labor_penalty = db.Column(db.Float, default=0.0) 
    penalized_salonist_ids = db.Column(db.String(100)) # e.g., "5,6"
    
    undo_salonist_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    wash_salonist_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    created_at = db.Column(db.DateTime, default=get_utc_now)

    # Relationships removed due to circular dependency issues
    # Use direct queries instead of relationships

# --- INVENTORY & SUPPLIERS ---

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(20), default='Shop', index=True) 
    category = db.Column(db.String(50), index=True) 
    stock_quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, nullable=False) 
    buying_price = db.Column(db.Float, nullable=False, default=0.0)
    min_selling_price = db.Column(db.Float) 
    reorder_level = db.Column(db.Integer, default=5) 
    branch = db.Column(db.String(20), index=True)
    last_updated = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    transactions = db.relationship('ProductTransaction', back_populates='product_obj', lazy=True)

class SupplierInvoice(db.Model):
    __tablename__ = 'supplier_invoices'
    
    id = db.Column(db.Integer, primary_key=True)
    supplier_name = db.Column(db.String(100), nullable=False)
    invoice_number = db.Column(db.String(50), unique=True, index=True)
    amount = db.Column(db.Float, nullable=False)
    date_received = db.Column(db.DateTime, default=get_utc_now)
    due_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='Pending', index=True) 
    branch = db.Column(db.String(50), index=True)
    items_summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    inventory_transactions = db.relationship('ProductTransaction', back_populates='invoice', lazy=True)

class ProductTransaction(db.Model):
    __tablename__ = 'product_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_no = db.Column(db.String(50), unique=True, nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey('supplier_invoices.id'))
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'))
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id')) 
    
    quantity = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Float) 
    department = db.Column(db.String(50)) 
    transaction_type = db.Column(db.String(20), index=True) # Restock, Sale, Internal Use
    timestamp = db.Column(db.DateTime, default=get_utc_now)    
    created_at = db.Column(db.DateTime, default=get_utc_now)

    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)

    invoice = db.relationship('SupplierInvoice', back_populates='inventory_transactions')
    product_obj = db.relationship('Product', back_populates='transactions')
    appointment = db.relationship('Appointment', backref='product_usage', lazy=True)

# --- FINANCE & RECONCILIATION ---

class Expense(db.Model):
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    expense_date = db.Column(db.DateTime, default=get_utc_now, index=True)
    month = db.Column(db.String(20), index=True)
    branch = db.Column(db.String(20), index=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)

class StaffDeduction(db.Model):
    __tablename__ = 'staff_deductions'
    
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id', name='fk_staff_deduction_worker'), nullable=True, index=True)
    branch = db.Column(db.String(20), nullable=False, index=True)
    deduction_type = db.Column(db.String(50), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    product_name = db.Column(db.String(100))
    target_role = db.Column(db.String(50), index=True)
    reason = db.Column(db.String(255))
    week_start = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)

    worker = db.relationship('Worker', backref='staff_deductions', lazy=True)
    
class MonthlyReconciliation(db.Model):
    __tablename__ = 'monthly_reconciliations'
    
    id = db.Column(db.Integer, primary_key=True)
    month_year = db.Column(db.String(20), nullable=False, index=True) 
    category = db.Column(db.String(20), nullable=False, index=True)   
    branch = db.Column(db.String(50), nullable=False, index=True)
    
    collected_fund = db.Column(db.Float, default=0.0)
    stock_invoice_total = db.Column(db.Float, default=0.0)
    utility_share = db.Column(db.Float, default=0.0)
    final_diff = db.Column(db.Float, default=0.0) 
    
    reconciled_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    created_at = db.Column(db.DateTime, default=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)

class DepartmentCategoryConfig(db.Model):
    __tablename__ = 'department_category_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    branch = db.Column(db.String(50), nullable=False, index=True)
    department = db.Column(db.String(30), nullable=False, index=True)
    categories_text = db.Column(db.String(255), default='')
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)

# --- SERVICE ORDERS ---

class ServiceOrder(db.Model):
    __tablename__ = 'service_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), nullable=False)
    client_phone = db.Column(db.String(20), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    
    # Financial details
    transacted_total = db.Column(db.Float, default=0.0)
    payment_method = db.Column(db.String(50))  # bank, mpesa, model
    is_model = db.Column(db.Boolean, default=False)
    receipt_no = db.Column(db.String(50))  # Transaction/receipt number
    
    # Status tracking
    status = db.Column(db.String(20), default='pending', index=True)  # pending, paid, completed
    branch = db.Column(db.String(20), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    paid_at = db.Column(db.DateTime)
    
    # NEW: Multi-tenant field
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    # Relationships
    created_by = db.relationship('Worker', foreign_keys=[created_by_id], backref='service_orders_created')
    client = db.relationship('Client', backref='service_orders')
    services = db.relationship('ServiceOrderItem', backref='service_order', lazy=True, cascade='all, delete-orphan')

class ServiceOrderItem(db.Model):
    """Individual services within a service order"""
    __tablename__ = 'service_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    service_order_id = db.Column(db.Integer, db.ForeignKey('service_orders.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    service_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    commission_rate = db.Column(db.Float, default=0.0)
    commission_amount = db.Column(db.Float, default=0.0)
    
    # Relationships
    service = db.relationship('Service', backref='order_items')

# --- USER LOADER ---

@login_manager.user_loader
def load_user(worker_id):
    return db.session.get(Worker, int(worker_id))
