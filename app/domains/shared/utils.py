"""
Shared utility functions used across multiple domains.
"""
from datetime import datetime, timedelta


def get_week_start(date_value):
    """Calculate the start of the week (Sunday) for a given date."""
    days_to_subtract = (date_value.weekday() + 1) % 7
    return (date_value - timedelta(days=days_to_subtract)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def get_fourth_sunday_week_start(date_value):
    """Calculate the start of the 4th Sunday week for a given date's month."""
    month_start = datetime(date_value.year, date_value.month, 1)
    first_sunday_offset = (6 - month_start.weekday()) % 7
    fourth_sunday = month_start + timedelta(days=first_sunday_offset + 21)
    return get_week_start(fourth_sunday)


def normalize_specialty(specialty_value):
    """Normalize specialty values for consistent matching."""
    value = (specialty_value or '').strip().lower()
    if 'cornrow' in value or 'conrow' in value:
        return 'Conrows'
    if 'braid' in value:
        return 'Braids'
    if 'undo' in value:
        return 'Undo'
    if 'nail' in value:
        return 'Nails'
    if 'wash' in value:
        return 'Wash'
    if 'makeup' in value:
        return 'Makeup'
    return 'Uncategorized'


# Tenant Payment Configuration System

def get_tenant_payment_options(tenant_id=None):
    """
    Get payment options configured for a specific tenant.
    """
    from flask_login import current_user

    if not tenant_id:
        tenant_id = current_user.salon_id

    # Default payment options if tenant doesn't have custom configuration
    default_options = [
        {'code': 'mpesa', 'name': 'M-Pesa', 'icon': 'fas fa-mobile-alt', 'is_default': True},
        {'code': 'bank', 'name': 'Bank', 'icon': 'fas fa-university', 'is_default': False},
        {'code': 'cash', 'name': 'Cash', 'icon': 'fas fa-money-bill', 'is_default': False},
        {'code': 'model', 'name': 'Model (No Payment)', 'icon': 'fas fa-user', 'is_default': False},
    ]

    # Try to get tenant-specific configuration from salon
    from app.models import Salon
    salon = Salon.query.filter_by(id=tenant_id).first()

    if salon and hasattr(salon, 'payment_config') and salon.payment_config:
        try:
            # Parse JSON configuration from salon
            import json
            custom_config = json.loads(salon.payment_config)

            # Merge with defaults, allowing tenant to override
            merged_options = []
            enabled_codes = [opt['code'] for opt in custom_config.get('enabled_methods', [])]

            for option in default_options:
                if option['code'] in enabled_codes:
                    # Find custom config for this method
                    custom_method = next((m for m in custom_config.get('enabled_methods', [])
                                       if m['code'] == option['code']), None)
                    if custom_method:
                        merged_option = option.copy()
                        merged_option.update({
                            'name': custom_method.get('name', option['name']),
                            'icon': custom_method.get('icon', option['icon']),
                            'is_default': custom_method.get('is_default', option['is_default'])
                        })
                        merged_options.append(merged_option)
                    else:
                        merged_options.append(option)

            return merged_options if merged_options else default_options
        except (json.JSONDecodeError, AttributeError):
            pass

    return default_options


def save_tenant_payment_config(tenant_id, payment_config):
    """
    Save payment configuration for a tenant.
    """
    from app.models import Salon
    from app import db
    import json

    salon = Salon.query.filter_by(id=tenant_id).first()
    if salon:
        salon.payment_config = json.dumps(payment_config)
        db.session.commit()
        return True
    return False
