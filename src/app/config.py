import os
from pathlib import Path
from dotenv import load_dotenv

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env file if present
load_dotenv(BASE_DIR / ".env")


class Config:
    """Base configuration shared across environments."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-secret-key-change-me")
    
    # Database Settings
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'open_invite.db'}"
    )
    # Normalize postgres:// and postgresql:// to postgresql+psycopg2:// for SQLAlchemy 2.0
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql+psycopg2://", 1
        )
    elif SQLALCHEMY_DATABASE_URI.startswith("postgresql://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # Document & S3 Storage
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")  # 'local' or 's3'
    raw_storage_path = os.environ.get("LOCAL_STORAGE_PATH", "uploads")
    if os.path.isabs(raw_storage_path):
        LOCAL_STORAGE_PATH = Path(raw_storage_path).resolve()
    else:
        LOCAL_STORAGE_PATH = (BASE_DIR / raw_storage_path).resolve()

    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "open-invite-storage")
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")

    # Email Communications
    EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "console")  # 'console', 'smtp', 'ses', 'sendgrid'
    SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 1025))
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@event-system.local")
    SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
    SES_SENDER_EMAIL = os.environ.get("SES_SENDER_EMAIL")


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    """Testing environment configuration."""
    DEBUG = False
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    STORAGE_BACKEND = "local"
    LOCAL_STORAGE_PATH = Path("/tmp/event_test_uploads")
    EMAIL_PROVIDER = "console"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production cloud configuration."""
    DEBUG = False
    TESTING = False
    # Ensure strong secret key in production
    SECRET_KEY = os.environ.get("SECRET_KEY")


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
