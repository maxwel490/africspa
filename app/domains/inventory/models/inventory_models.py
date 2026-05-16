"""Inventory domain models - Product, Supplier, SupplierInvoice, ProductTransaction."""
from datetime import datetime, timezone
from app import db


# Helper for UTC time to ensure Python 3.12 compatibility
def get_utc_now():
    return datetime.now(timezone.utc)


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
