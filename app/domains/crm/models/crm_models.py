"""CRM domain models - Client, Message, SupportTicket."""
from datetime import datetime, timezone
from app import db


# Helper for UTC time to ensure Python 3.12 compatibility
def get_utc_now():
    return datetime.now(timezone.utc)


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
