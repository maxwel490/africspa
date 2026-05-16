# --- SAAS SUBSCRIPTION MODELS ---

class SubscriptionPlan(db.Model):
    """Subscription plans for salons"""
    __tablename__ = 'subscription_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # basic, professional, enterprise
    display_name = db.Column(db.String(100), nullable=False)
    monthly_price = db.Column(db.Float, nullable=False)
    yearly_price = db.Column(db.Float, nullable=False)
    max_branches = db.Column(db.Integer, nullable=False)
    max_staff = db.Column(db.Integer, nullable=False)
    max_clients = db.Column(db.Integer, nullable=False)
    features = db.Column(db.Text)  # JSON string of features
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<SubscriptionPlan {self.display_name}>'

class Subscription(db.Model):
    """Active subscriptions for salons"""
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    auto_renew = db.Column(db.Boolean, default=True)
    payment_method = db.Column(db.String(50))  # mpesa, card, bank
    amount_paid = db.Column(db.Float, nullable=False)
    payment_reference = db.Column(db.String(100))
    
    # Relationships
    salon = db.relationship('Salon', backref='subscriptions')
    plan = db.relationship('SubscriptionPlan', backref='subscriptions')
    
    def is_expired(self):
        return self.end_date < datetime.utcnow()
    
    def days_until_expiry(self):
        if self.is_expired():
            return 0
        return (self.end_date - datetime.utcnow()).days

class Payment(db.Model):
    """Payment records for subscriptions"""
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    # Relationships
    subscription = db.relationship('Subscription', backref='payments')

# --- INITIAL SUBSCRIPTION PLANS DATA ---
def init_subscription_plans():
    """Initialize default subscription plans"""
    plans = [
        {
            'name': 'basic',
            'display_name': 'Basic',
            'monthly_price': 5000,  # KES 5,000/month
            'yearly_price': 50000,  # KES 50,000/year (2 months free)
            'max_branches': 1,
            'max_staff': 5,
            'max_clients': 500,
            'features': json.dumps([
                'Appointment Booking',
                'Basic Inventory Management',
                'Staff Management',
                'Client Management',
                'Basic Reports',
                'Email Support'
            ])
        },
        {
            'name': 'professional',
            'display_name': 'Professional',
            'monthly_price': 15000,  # KES 15,000/month
            'yearly_price': 150000,  # KES 150,000/year (2 months free)
            'max_branches': 3,
            'max_staff': 20,
            'max_clients': 2000,
            'features': json.dumps([
                'Everything in Basic',
                'Multi-Branch Management',
                'Advanced Analytics',
                'Commission Tracking',
                'Product Management',
                'Financial Reports',
                'SMS Notifications',
                'Priority Support'
            ])
        },
        {
            'name': 'enterprise',
            'display_name': 'Enterprise',
            'monthly_price': 40000,  # KES 40,000/month
            'yearly_price': 400000,  # KES 400,000/year (2 months free)
            'max_branches': 10,
            'max_staff': 100,
            'max_clients': 10000,
            'features': json.dumps([
                'Everything in Professional',
                'Unlimited Branches',
                'Custom Reports',
                'API Access',
                'White Label Options',
                'Dedicated Support',
                'Advanced Security',
                'Custom Integrations'
            ])
        }
    ]
    
    for plan_data in plans:
        existing = SubscriptionPlan.query.filter_by(name=plan_data['name']).first()
        if not existing:
            plan = SubscriptionPlan(**plan_data)
            db.session.add(plan)
    
    db.session.commit()
