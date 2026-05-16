from flask import Blueprint

# Define the blueprint
accountant_bp = Blueprint('accountant', __name__)

# Import routes at the end
from app.accountant import routes