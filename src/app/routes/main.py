from flask import Blueprint, render_template, current_app

main_bp = Blueprint("main", __name__)


@main_bp.route("/", methods=["GET"])
def index():
    """Application landing page."""
    context = {
        "title": "Event Invitation Management System",
        "storage_backend": current_app.config.get("STORAGE_BACKEND"),
        "email_provider": current_app.config.get("EMAIL_PROVIDER"),
        "s3_bucket": current_app.config.get("S3_BUCKET_NAME"),
    }
    return render_template("index.html", **context)
