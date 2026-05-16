"""Auth routes - thin wrapper. Handlers in app/domains/authentication/routes/."""
from app.auth import auth_bp
from app.domains.authentication.routes import auth_routes  # noqa: F401
