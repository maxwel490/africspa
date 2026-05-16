from flask import Blueprint

# Define the blueprint
main_bp = Blueprint('main', __name__)

# Import domain routes to register handlers on main_bp
from app.domains.tenancy.routes import public_routes  # noqa: F401
