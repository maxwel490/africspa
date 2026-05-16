"""Admin routes - thin wrapper. Handlers in app/domains/*/routes/."""
from app.admin import admin_bp  # noqa: F401
from app.domains.analytics.routes import admin_analytics_routes  # noqa: F401
from app.domains.tenancy.routes import branch_routes  # noqa: F401
from app.domains.finance.routes import admin_finance_routes  # noqa: F401
from app.domains.inventory.routes import stock_routes  # noqa: F401
from app.domains.scheduling.routes import service_management_routes  # noqa: F401
from app.domains.billing.routes import payment_settings_routes  # noqa: F401
from app.domains.crm.routes import admin_chat_routes  # noqa: F401
