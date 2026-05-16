import datetime
import os
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config 
from flask_migrate import Migrate
from sqlalchemy import MetaData

naming_convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

db = SQLAlchemy(metadata=MetaData(naming_convention=naming_convention))
login_manager = LoginManager()
migrate = Migrate()

# MODIFIED: Added arguments to the function
def create_app(template_folder='templates', static_folder='static'):
    app = Flask(__name__, 
                template_folder=template_folder, 
                static_folder=static_folder)
    os.makedirs(app.instance_path, exist_ok=True)
    
    app.config.from_object(Config)
    
    # Initialize security components
    from app.security import init_security
    init_security(app)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True) 
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Blueprint Registrations
    from app.auth.routes import auth_bp
    from app.auth.oauth_routes import oauth_bp
    from app.admin import admin_bp
    from app.accountant.routes import accountant_bp 
    from app.salonist.routes import salonist_bp
    from app.main.routes import main_bp
    from app.superadmin.routes import superadmin_bp
    from app.routes.pricing_management import superadmin_pricing_bp
    from app.controllers.subscription_payment import subscription_payment_bp
    from app.routes.public_chat import public_chat_bp
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(oauth_bp, url_prefix='/oauth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(accountant_bp, url_prefix='/accountant') 
    app.register_blueprint(salonist_bp, url_prefix='/salonist')
    app.register_blueprint(main_bp)
    app.register_blueprint(superadmin_bp, url_prefix='/superadmin')
    app.register_blueprint(superadmin_pricing_bp, url_prefix='/superadmin/pricing')
    app.register_blueprint(subscription_payment_bp)
    app.register_blueprint(public_chat_bp, url_prefix='/public-chat')
    
    # Initialize OAuth providers after app is fully configured
    from app.auth.oauth_providers import oauth_manager
    with app.app_context():
        oauth_manager.init_providers(app)

    from app.models import Worker
    @login_manager.user_loader
    def load_user(worker_id):
        return db.session.get(Worker, int(worker_id))

    # Initialize tenant isolation middleware
    from app.middleware.tenant_isolation import TenantIsolationMiddleware
    TenantIsolationMiddleware(app)

    # Add tenant context to all templates
    @app.context_processor
    def inject_tenant_context():
        from app.middleware.tenant_isolation import tenant_aware_template_context
        return tenant_aware_template_context()

    @app.context_processor
    def inject_now():
        return {'now': datetime.datetime.utcnow()}
    
    @app.route('/')
    def index():
        return redirect(url_for('main.index'))
    
    return app