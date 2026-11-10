import sys
from datetime import datetime, timezone
from flask import Blueprint, jsonify, current_app
from sqlalchemy import text
from src.app import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Healthcheck endpoint for Docker and AWS App Runner / ALB."""
    db_status = "healthy"
    status_code = 200

    try:
        # Check database connectivity with lightweight ping
        db.session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        status_code = 503

    return (
        jsonify(
            {
                "status": "ok" if status_code == 200 else "degraded",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "environment": current_app.config.get("ENV", "development"),
                "python_version": sys.version.split()[0],
                "storage_backend": current_app.config.get("STORAGE_BACKEND"),
                "email_provider": current_app.config.get("EMAIL_PROVIDER"),
                "database": db_status,
            }
        ),
        status_code,
    )
