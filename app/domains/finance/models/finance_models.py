"""Finance domain models - Expense, BackbarGroup, StaffDeduction, MonthlyReconciliation"""
from datetime import datetime, timezone
from app import db

def get_utc_now():
    return datetime.now(timezone.utc)


class Expense(db.Model):
    """Multi-tenant expense management"""
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    
    branch = db.Column(db.String(20), index=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    expense_date = db.Column(db.Date, nullable=False, index=True)
    month = db.Column(db.String(20), index=True)
    receipt_no = db.Column(db.String(50))
    invoice_no = db.Column(db.String(50))
    vendor = db.Column(db.String(100))
    payment_method = db.Column(db.String(50))
    
    approved_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    approved_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    receipt_image = db.Column(db.String(255))
    
    status = db.Column(db.String(20), default='pending', index=True)
    is_reimbursable = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    def __repr__(self):
        return f'<Expense {self.description}>'


class BackbarGroup(db.Model):
    __tablename__ = 'backbar_groups'
    id = db.Column(db.Integer, primary_key=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    target_specialties = db.Column(db.Text)
    target_employment_types = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    color = db.Column(db.String(20), default='primary')
    icon = db.Column(db.String(50), default='bi-people')
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    salon = db.relationship('Salon', backref=db.backref('backbar_groups', lazy=True, cascade='all, delete-orphan'))
    
    def get_target_specialties(self):
        import json
        if self.target_specialties:
            try:
                return json.loads(self.target_specialties)
            except:
                return []
        return []
    
    def set_target_specialties(self, specialties_list):
        import json
        self.target_specialties = json.dumps(specialties_list)
    
    def get_target_employment_types(self):
        import json
        if self.target_employment_types:
            try:
                return json.loads(self.target_employment_types)
            except:
                return []
        return []
    
    def set_target_employment_types(self, types_list):
        import json
        self.target_employment_types = json.dumps(types_list)
    
    def get_eligible_workers(self, branch):
        from app.models import Worker
        
        query = Worker.query.filter_by(branch=branch, role='salonist')
        
        specialties = self.get_target_specialties()
        if specialties:
            query = query.filter(Worker.specialty.in_(specialties))
        
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
    deduction_type = db.Column(db.String(50), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    reason = db.Column(db.String(255))
    product_name = db.Column(db.String(100))
    target_role = db.Column(db.String(100))
    inventory_type = db.Column(db.String(20), default='salon')
    backbar_group_id = db.Column(db.Integer, db.ForeignKey('backbar_groups.id'), nullable=True, index=True)
    week_start = db.Column(db.Date, nullable=False, index=True)
    month_year = db.Column(db.String(20), index=True)
    
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    worker = db.relationship('Worker', foreign_keys=[worker_id], backref='staff_deductions')
    backbar_group = db.relationship('BackbarGroup', backref=db.backref('deductions', lazy=True))
    created_by = db.relationship('Worker', foreign_keys=[created_by_id], backref='created_deductions')
    
    def get_remaining_balance(self):
        return self.balance_amount - self.paid_amount
    
    def is_overdue(self):
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
    
    opening_balance = db.Column(db.Float, default=0.0)
    collected_fund = db.Column(db.Float, default=0.0)
    stock_invoice_total = db.Column(db.Float, default=0.0)
    utility_share = db.Column(db.Float, default=0.0)
    other_expenses = db.Column(db.Float, default=0.0)
    staff_commissions = db.Column(db.Float, default=0.0)
    staff_deductions = db.Column(db.Float, default=0.0)
    final_diff = db.Column(db.Float, default=0.0) 
    
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    
    status = db.Column(db.String(20), default='pending', index=True)
    notes = db.Column(db.Text)
    
    reconciled_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    reconciled_at = db.Column(db.DateTime, default=get_utc_now)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    reconciled_by = db.relationship('Worker', foreign_keys=[reconciled_by_id], backref='reconciliations')
    
    def get_expected_balance(self):
        return (self.opening_balance + self.collected_fund - 
                self.stock_invoice_total - self.utility_share - self.other_expenses)
    
    def get_variance(self):
        expected = self.get_expected_balance()
        actual = expected - self.staff_commissions + self.staff_deductions
        return actual - self.final_diff
    
    def __repr__(self):
        return f'<MonthlyReconciliation {self.month_year} - {self.category}>'
