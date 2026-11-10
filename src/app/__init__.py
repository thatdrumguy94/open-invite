import os
from flask import Flask, session, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from src.app.config import config_by_name, Config

# Global extensions
db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name=None):
    """Application factory for Flask web service."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development").lower()

    app = Flask(__name__)
    selected_config = config_by_name.get(config_name, Config)
    app.config.from_object(selected_config)

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
