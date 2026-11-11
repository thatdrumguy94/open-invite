import os
from flask import Flask, session, g, request, redirect, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix
from src.app.config import config_by_name, Config

# Global extensions
db = SQLAlchemy()
migrate = Migrate()


class _CloudFrontProtoMiddleware:
    """Normalize CloudFront-Forwarded-Proto header to X-Forwarded-Proto when absent."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        if (
            "HTTP_X_FORWARDED_PROTO" not in environ
            and "HTTP_CLOUDFRONT_FORWARDED_PROTO" in environ
        ):
            environ["HTTP_X_FORWARDED_PROTO"] = environ["HTTP_CLOUDFRONT_FORWARDED_PROTO"]
        return self.wsgi_app(environ, start_response)


def create_app(config_name=None):
    """Application factory for Flask web service."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development").lower()

    app = Flask(__name__)
    selected_config = config_by_name.get(config_name, Config)
    app.config.from_object(selected_config)

    # Trust X-Forwarded-* headers from Nginx, AWS ALB, App Runner, or CloudFront
    if app.config.get("TRUST_PROXY_HEADERS", True):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config.get("PROXY_FIX_X_FOR", 1),
            x_proto=app.config.get("PROXY_FIX_X_PROTO", 1),
            x_host=app.config.get("PROXY_FIX_X_HOST", 1),
            x_port=app.config.get("PROXY_FIX_X_PORT", 1),
            x_prefix=app.config.get("PROXY_FIX_X_PREFIX", 1),
        )
        app.wsgi_app = _CloudFrontProtoMiddleware(app.wsgi_app)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Ensure instance and upload directories exist
    os.makedirs(app.instance_path, exist_ok=True)
    if app.config.get("STORAGE_BACKEND") == "local":
        upload_path = app.config.get("LOCAL_STORAGE_PATH")
        if upload_path:
            upload_path.mkdir(parents=True, exist_ok=True)

    # Register models with metadata
    from src.app import models
    from src.app.models.user import User

    # Enforce HTTPS redirect (exempting internal health probes)
    @app.before_request
    def enforce_https():
        if not current_app.config.get("FORCE_HTTPS", False):
            return None
        if request.is_secure:
            return None
        exempt_paths = current_app.config.get("HTTPS_EXEMPT_PATHS", ("/health",))
        if request.path in exempt_paths:
            return None
        if request.url.startswith("http://"):
            target_url = "https://" + request.url[len("http://") :]
            status_code = 301 if request.method in ("GET", "HEAD") else 308
            return redirect(target_url, code=status_code)
        return None

    # Authentication context processor and before_request hook
    @app.before_request
    def load_logged_in_user():
        user_id = session.get("user_id")
        if user_id is None:
            g.current_user = None
        else:
            g.current_user = db.session.get(User, user_id)

    @app.context_processor
    def inject_user():
        return dict(current_user=getattr(g, "current_user", None))

    @app.after_request
    def add_security_headers(response):
        if not current_app.config.get("ENABLE_SECURITY_HEADERS", True):
            return response

        # Emit HSTS only over HTTPS requests per RFC 6797
        if request.is_secure and current_app.config.get("HSTS_ENABLED", True):
            max_age = current_app.config.get("HSTS_MAX_AGE", 31536000)
            hsts_parts = [f"max-age={max_age}"]
            if current_app.config.get("HSTS_INCLUDE_SUBDOMAINS", True):
                hsts_parts.append("includeSubDomains")
            if current_app.config.get("HSTS_PRELOAD", False):
                hsts_parts.append("preload")
            response.headers.setdefault(
                "Strict-Transport-Security", "; ".join(hsts_parts)
            )

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        return response

    # Register CLI commands
    from src.app.cli import init_db_command, seed_db_command
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_db_command)

    # Register application blueprints
    from src.app.routes.health import health_bp
    from src.app.routes.main import main_bp
    from src.app.routes.auth import auth_bp
    from src.app.routes.events import events_bp
    from src.app.routes.guests import guests_bp
    from src.app.routes.rsvp import rsvp_bp
    from src.app.routes.communications import communications_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(guests_bp)
    app.register_blueprint(rsvp_bp)
    app.register_blueprint(communications_bp)

    return app
