from flask import Blueprint

superadmin_bp = Blueprint('superadmin', __name__, 
                         template_folder='../templates/superadmin',
                         url_prefix='/superadmin')

# Import domain routes to register handlers on superadmin_bp
from app.domains.tenancy.routes import superadmin_routes  # noqa: F401
