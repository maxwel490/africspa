from flask import Blueprint

# Define the blueprint
admin_bp = Blueprint('admin', __name__)

# Import domain routes to register handlers on admin_bp
from app.domains.analytics.routes import admin_analytics_routes  # noqa: F401
from app.domains.tenancy.routes import branch_routes  # noqa: F401
from app.domains.finance.routes import admin_finance_routes  # noqa: F401
from app.domains.inventory.routes import stock_routes  # noqa: F401
from app.domains.scheduling.routes import service_management_routes  # noqa: F401
from app.domains.billing.routes import payment_settings_routes  # noqa: F401
from app.domains.crm.routes import admin_chat_routes  # noqa: F401
