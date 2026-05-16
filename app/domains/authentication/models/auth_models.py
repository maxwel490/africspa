"""Authentication domain models - Worker (User)"""
from datetime import datetime, timezone, timedelta
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

def get_utc_now():
    return datetime.now(timezone.utc)


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
    role = db.Column(db.String(20), nullable=False, index=True)
    
    branch = db.Column(db.String(20), index=True) 
    specialty = db.Column(db.String(50))
    base_salary = db.Column(db.Float, default=0.0)
    commission_rate = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    last_login = db.Column(db.DateTime)
    
    salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=True)
    
    created_by_id = db.Column(db.Integer, db.ForeignKey('workers.id', name='fk_worker_creator'), nullable=True)
    profile_image = db.Column(db.String(255))
    bio = db.Column(db.Text)
    
    permissions = db.Column(db.Text)
    preferences = db.Column(db.Text)
    language = db.Column(db.String(10), default='en')
    
    password_changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    password_history = db.Column(db.Text)
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime)
    is_locked = db.Column(db.Boolean, default=False)
    locked_until = db.Column(db.DateTime)
    password_expired = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        from app.security.password_policy import password_policy
        import json
        
        validation = password_policy.validate_password(password, self.username, self.email)
        if not validation['valid']:
            raise ValueError(f"Password validation failed: {'; '.join(validation['errors'])}")
        
        if self.password_hash:
            import hashlib
            if not self.password_history:
                self.password_history = json.dumps([])
            
            history = json.loads(self.password_history)
            history.append({
                'hash': hashlib.sha256(self.password_hash.encode()).hexdigest(),
                'changed_at': datetime.utcnow().isoformat()
            })
            
            if len(history) > password_policy.password_history:
                history = history[-password_policy.password_history:]
            
            self.password_history = json.dumps(history)
        
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.utcnow()
        self.password_expired = False
        self.failed_login_attempts = 0
        self.is_locked = False
        self.locked_until = None

    def check_password(self, password):
        from app.security.password_policy import password_policy
        
        if self.is_locked and self.locked_until and datetime.utcnow() < self.locked_until:
            return False
        
        if not check_password_hash(self.password_hash, password):
            self._record_failed_login()
            return False
        
        if self.failed_login_attempts > 0:
            self.failed_login_attempts = 0
            self.last_failed_login = None
            self.is_locked = False
            self.locked_until = None
        
        if password_policy.is_password_expired(self.password_changed_at):
            self.password_expired = True
        
        return True

    def _record_failed_login(self):
        """Record failed login attempt"""
        from app.security.password_policy import password_policy
        from flask import current_app
        
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.utcnow()
        
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
        from app.domains.scheduling.models.scheduling_models import Appointment
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


@login_manager.user_loader
def load_user(worker_id):
    return db.session.get(Worker, int(worker_id))
