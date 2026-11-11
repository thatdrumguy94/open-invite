import os
from pathlib import Path
from dotenv import load_dotenv

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env file if present
load_dotenv(BASE_DIR / ".env")


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse boolean environment variables safely."""
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_int(value: str | None, default: int = 1) -> int:
    """Parse non-negative integer environment variables safely."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


class Config:
    """Base configuration shared across environments."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-secret-key-change-me")

    # HTTPS, Reverse Proxy & Cookie Security Settings
    FORCE_HTTPS = _parse_bool(os.environ.get("FORCE_HTTPS"), False)
    PREFERRED_URL_SCHEME = os.environ.get(
        "PREFERRED_URL_SCHEME", "https" if FORCE_HTTPS else "http"
    )
    HTTPS_EXEMPT_PATHS = ("/health",)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _parse_bool(
        os.environ.get("SESSION_COOKIE_SECURE"), FORCE_HTTPS
    )
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    ENABLE_SECURITY_HEADERS = _parse_bool(
        os.environ.get("ENABLE_SECURITY_HEADERS"), True
    )
    HSTS_ENABLED = _parse_bool(os.environ.get("HSTS_ENABLED"), True)
    HSTS_MAX_AGE = _parse_int(os.environ.get("HSTS_MAX_AGE"), 31536000)
    HSTS_INCLUDE_SUBDOMAINS = _parse_bool(
        os.environ.get("HSTS_INCLUDE_SUBDOMAINS"), True
    )
    HSTS_PRELOAD = _parse_bool(os.environ.get("HSTS_PRELOAD"), False)

    TRUST_PROXY_HEADERS = _parse_bool(os.environ.get("TRUST_PROXY_HEADERS"), True)
    PROXY_FIX_X_FOR = _parse_int(os.environ.get("PROXY_FIX_X_FOR"), 1)
    PROXY_FIX_X_PROTO = _parse_int(os.environ.get("PROXY_FIX_X_PROTO"), 1)
    PROXY_FIX_X_HOST = _parse_int(os.environ.get("PROXY_FIX_X_HOST"), 1)
    PROXY_FIX_X_PORT = _parse_int(os.environ.get("PROXY_FIX_X_PORT"), 1)
    PROXY_FIX_X_PREFIX = _parse_int(os.environ.get("PROXY_FIX_X_PREFIX"), 1)

    TLS_ENABLED = _parse_bool(os.environ.get("TLS_ENABLED"), False)
    SSL_CERTFILE = os.environ.get("SSL_CERTFILE")
    SSL_KEYFILE = os.environ.get("SSL_KEYFILE")
    
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
    FORCE_HTTPS = False
    PREFERRED_URL_SCHEME = "http"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    TRUST_PROXY_HEADERS = True


class ProductionConfig(Config):
    """Production cloud configuration."""
    DEBUG = False
    TESTING = False
    # Ensure strong secret key in production
    SECRET_KEY = os.environ.get("SECRET_KEY")
    FORCE_HTTPS = _parse_bool(os.environ.get("FORCE_HTTPS"), True)
    PREFERRED_URL_SCHEME = os.environ.get(
        "PREFERRED_URL_SCHEME", "https" if FORCE_HTTPS else "http"
    )
    SESSION_COOKIE_SECURE = _parse_bool(
        os.environ.get("SESSION_COOKIE_SECURE"), FORCE_HTTPS
    )
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
