from flask import Blueprint

# Define the blueprint
accountant_bp = Blueprint('accountant', __name__)

# Import domain routes to register handlers on accountant_bp
from app.domains.analytics.routes import accountant_analytics_routes  # noqa: F401
from app.domains.inventory.routes import inventory_routes  # noqa: F401
from app.domains.finance.routes import accountant_finance_routes  # noqa: F401
from app.domains.scheduling.routes import service_routes  # noqa: F401
from app.domains.crm.routes import client_routes  # noqa: F401
