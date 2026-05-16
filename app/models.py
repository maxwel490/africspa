"""
Compatibility re-export layer.
All models are now defined in app/domains/*/models/ but re-exported here
for backward compatibility with existing imports.
"""
from datetime import datetime, timezone
from app import db, login_manager

# --- Tenancy Domain ---
from app.domains.tenancy.models.tenant_models import Salon, Branch

# --- Authentication Domain ---
from app.domains.authentication.models.auth_models import Worker, load_user

# --- CRM Domain ---
from app.domains.crm.models.crm_models import Client, Message, SupportTicket

# --- Scheduling Domain ---
from app.domains.scheduling.models.scheduling_models import (
    Service, Appointment, RectificationLog, ServiceOrder, ServiceOrderItem,
    DepartmentCategoryConfig
)

# --- Inventory Domain ---
from app.domains.inventory.models.inventory_models import (
    Product, Supplier, SupplierInvoice, ProductTransaction
)

# --- Finance Domain ---
from app.domains.finance.models.finance_models import (
    Expense, BackbarGroup, StaffDeduction, MonthlyReconciliation
)

# --- Billing Domain ---
from app.domains.billing.models.billing_models import (
    BillingRecord, PricingConfig, PricingHistory, PaymentConfig, ContactConfig
)

# --- Analytics Domain ---
from app.domains.analytics.models.analytics_models import SystemConfig


# --- Helper function ---
def get_utc_now():
    return datetime.now(timezone.utc)


# --- Utility Functions ---
def get_salon_by_slug(slug):
    """Get salon by slug for subdomain routing"""
    return Salon.query.filter_by(slug=slug, is_active=True).first()

def get_user_salons(user):
    """Get all salons a user has access to"""
    if user.role == 'superadmin':
        return Salon.query.all()
    else:
        salon = Salon.query.get(user.salon_id)
        return [salon] if salon else []

def validate_subscription(salon, feature=None):
    """Validate if salon's subscription supports a feature"""
    if not salon or not salon.is_active:
        return False
    
    if salon.subscription_expires and salon.subscription_expires < datetime.utcnow():
        return False
    
    feature_map = {
        'appointments': salon.feature_appointments,
        'inventory': salon.feature_inventory,
        'reporting': salon.feature_reporting,
        'api_access': salon.feature_api_access,
        'custom_branding': salon.feature_custom_branding,
        'multi_branch': salon.feature_multi_branch
    }
    
    if feature and feature not in feature_map:
        return False
    
    return feature_map.get(feature, True) if feature else True

def calculate_total_monthly_subscription_revenue():
    """Calculate total monthly subscription revenue - $30 per branch"""
    total_revenue = 0
    
    salons = Salon.query.filter_by(is_active=True).all()
    for salon in salons:
        branch_count = len([b for b in salon.branches if b.is_active]) if salon.branches else 1
        total_revenue += branch_count * 30 * 120
    
    return total_revenue
