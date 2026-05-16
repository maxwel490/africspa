"""Scheduling domain models - Service, Appointment, ServiceOrder, etc."""
from datetime import datetime, timezone
from app import db


# Helper for UTC time to ensure Python 3.12 compatibility
def get_utc_now():
    return datetime.now(timezone.utc)


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
