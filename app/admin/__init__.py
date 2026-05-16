from flask import Blueprint

# Define the blueprint
admin_bp = Blueprint('admin', __name__)

# Import routes at the end to avoid circular imports
from app.admin import routes