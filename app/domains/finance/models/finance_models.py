"""Finance domain models - Expense, BackbarGroup, StaffDeduction, MonthlyReconciliation."""
from datetime import datetime, timezone
from app import db


# Helper for UTC time to ensure Python 3.12 compatibility
def get_utc_now():
    return datetime.now(timezone.utc)


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
