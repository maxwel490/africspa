from flask import Blueprint

# Initialize the blueprint here so it's available to the whole package
auth_bp = Blueprint('auth', __name__)

# Import domain routes to register handlers on auth_bp
from app.domains.authentication.routes import auth_routes  # noqa: F401
