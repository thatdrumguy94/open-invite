import os
from pathlib import Path
from src.app import create_app
from src.app.tls import ensure_self_signed_cert

env_name = os.environ.get("FLASK_ENV", "development").lower()
app = create_app(env_name)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    tls_enabled = os.environ.get("TLS_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    certfile = os.environ.get("SSL_CERTFILE")
    keyfile = os.environ.get("SSL_KEYFILE")
    ssl_context = None
    if certfile and keyfile:
        ssl_context = (certfile, keyfile)
    elif tls_enabled:
        ssl_context = ensure_self_signed_cert(
            Path(app.instance_path) / "certs",
            common_name=os.environ.get("TLS_DOMAIN", "localhost"),
        )
    app.run(
        host="0.0.0.0",
        port=port,
        debug=(env_name == "development"),
        ssl_context=ssl_context,
    )
