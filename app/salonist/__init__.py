from flask import Blueprint

# Define the blueprint
salonist_bp = Blueprint('salonist', __name__)

# Import routes at the end
from app.salonist import routes