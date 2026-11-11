import os
import subprocess
from pathlib import Path
from typing import Tuple


def ensure_self_signed_cert(
    cert_dir: Path,
    common_name: str = "localhost",
    days: int = 365,
) -> Tuple[str, str]:
    """Generate a self-signed TLS certificate and key with SANs if missing."""
    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "server.crt"
    key_path = cert_dir / "server.key"

    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)

    san_entries = ["DNS:localhost", "DNS:*.localhost", "IP:127.0.0.1"]
    san_name = (common_name or "").strip()
    if san_name and san_name != "localhost":
        san_entries.append(f"DNS:{san_name}")

    cmd = [
        "openssl",
        "req",
        "-x509",
        "-nodes",
        "-newkey",
        "rsa:2048",
        "-keyout",
        str(key_path),
        "-out",
        str(cert_path),
        "-days",
        str(days),
        "-subj",
        f"/C=US/ST=Texas/L=San Antonio/O=OpenInvite/CN={san_name or 'localhost'}",
        "-addext",
        f"subjectAltName={','.join(san_entries)}",
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    os.chmod(key_path, 0o600)
    return str(cert_path), str(key_path)
