"""Analytics domain models - SystemConfig"""
from datetime import datetime, timezone
from app import db

def get_utc_now():
    return datetime.now(timezone.utc)


class SystemConfig(db.Model):
    """System-wide configuration settings"""
    __tablename__ = 'system_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    
    config_type = db.Column(db.String(50))
    is_public = db.Column(db.Boolean, default=False)
    is_editable = db.Column(db.Boolean, default=True)
    
    min_value = db.Column(db.Float)
    max_value = db.Column(db.Float)
    allowed_values = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('workers.id'))
    
    def get_parsed_value(self):
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
