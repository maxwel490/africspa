from flask import Blueprint

# Initialize the blueprint here so it's available to the whole package
auth_bp = Blueprint('auth', __name__)

# Import routes at the bottom to avoid circular imports
from app.auth import routes