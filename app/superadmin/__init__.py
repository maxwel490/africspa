from flask import Blueprint

superadmin_bp = Blueprint('superadmin', __name__, 
                         template_folder='../templates/superadmin',
                         url_prefix='/superadmin')
