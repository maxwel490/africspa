from flask import Blueprint

# Define the blueprint
salonist_bp = Blueprint('salonist', __name__)

# Import domain routes to register handlers on salonist_bp
from app.domains.scheduling.routes import salonist_routes  # noqa: F401
