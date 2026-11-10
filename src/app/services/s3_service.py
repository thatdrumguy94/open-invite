import io
import os
from pathlib import Path
from typing import BinaryIO, Union
from flask import current_app, url_for
import boto3
from botocore.exceptions import ClientError, NoCredentialsError


class StorageService:
    """Unified storage interface supporting both Amazon S3 and local filesystem fallback."""

    def __init__(self, backend: str = None, bucket_name: str = None, region: str = None, local_path: Path = None):
        self.backend = backend or os.environ.get("STORAGE_BACKEND", "local")
        self.bucket_name = bucket_name or os.environ.get("S3_BUCKET_NAME", "open-invite-storage")
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        resolved_path = local_path or os.environ.get("LOCAL_STORAGE_PATH", "./uploads")
        self.local_path = Path(resolved_path).resolve()

        # Initialize boto3 S3 client if in S3 mode
        self.s3_client = None
        if self.backend == "s3":
            try:
                self.s3_client = boto3.client("s3", region_name=self.region)
            except Exception as e:
                print(f"Warning: Failed to initialize Boto3 S3 client ({e}). Falling back to local storage.")
                self.backend = "local"

        if self.backend == "local":
            self.local_path.mkdir(parents=True, exist_ok=True)

    def save_file(
        self,
        file_data: Union[bytes, BinaryIO],
        key: str,
        content_type: str = "application/pdf",
    ) -> str:
        """Save file bytes or stream to S3 or local disk. Returns the storage key/relative path."""
        # Normalize key path (remove leading slashes)
        normalized_key = key.lstrip("/").replace("\\", "/")

        if isinstance(file_data, bytes):
            buffer = io.BytesIO(file_data)
        else:
            buffer = file_data

        if self.backend == "s3" and self.s3_client:
            try:
                buffer.seek(0)
                self.s3_client.upload_fileobj(
                    buffer,
                    self.bucket_name,
                    normalized_key,
                    ExtraArgs={"ContentType": content_type},
                )
                return normalized_key
            except (ClientError, NoCredentialsError) as e:
                print(f"S3 upload error for {normalized_key}: {e}. Falling back to local storage.")

        # Local storage fallback
        dest_path = self.local_path / normalized_key
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        buffer.seek(0)
        with open(dest_path, "wb") as f:
            f.write(buffer.read())

        return normalized_key

    def get_file(self, key: str) -> bytes:
        """Retrieve file raw bytes from S3 or local disk."""
        normalized_key = key.lstrip("/").replace("\\", "/")

        if self.backend == "s3" and self.s3_client:
            try:
                buffer = io.BytesIO()
                self.s3_client.download_fileobj(self.bucket_name, normalized_key, buffer)
                buffer.seek(0)
                return buffer.read()
            except ClientError as e:
                print(f"S3 download error for {normalized_key}: {e}")

        # Local fallback
        dest_path = self.local_path / normalized_key
        if dest_path.exists():
            with open(dest_path, "rb") as f:
                return f.read()

        raise FileNotFoundError(f"File key '{normalized_key}' not found in storage.")

    def get_url(self, key: str, expiration: int = 3600) -> str:
        """Generate a presigned download URL for S3, or a local endpoint URL."""
        if not key:
            return ""

        normalized_key = key.lstrip("/").replace("\\", "/")

        if self.backend == "s3" and self.s3_client:
            try:
                url = self.s3_client.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": normalized_key,
                    },
                    ExpiresIn=expiration,
                )
                return url
            except (ClientError, NoCredentialsError) as e:
                print(f"Error generating presigned URL for {normalized_key}: {e}")

        # Local fallback: return relative URL served by application
        try:
            return url_for("events.serve_storage_file", key=normalized_key, _external=True)
        except (RuntimeError, Exception):
            # Outside of request context or routing lookup failure
            return f"/events/storage/{normalized_key}"

    def delete_file(self, key: str) -> bool:
        """Delete file from S3 or local disk."""
        normalized_key = key.lstrip("/").replace("\\", "/")

        if self.backend == "s3" and self.s3_client:
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=normalized_key)
                return True
            except ClientError as e:
                print(f"Error deleting S3 object {normalized_key}: {e}")
                return False

        dest_path = self.local_path / normalized_key
        if dest_path.exists():
            dest_path.unlink()
            return True
        return False

    def file_exists(self, key: str) -> bool:
        """Check if file exists in S3 or local disk."""
        normalized_key = key.lstrip("/").replace("\\", "/")

        if self.backend == "s3" and self.s3_client:
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=normalized_key)
                return True
            except ClientError:
                return False

        return (self.local_path / normalized_key).exists()


def get_storage_service() -> StorageService:
    """Factory helper to obtain configured StorageService from current Flask application context."""
    if current_app:
        return StorageService(
            backend=current_app.config.get("STORAGE_BACKEND"),
            bucket_name=current_app.config.get("S3_BUCKET_NAME"),
            region=current_app.config.get("AWS_REGION"),
            local_path=current_app.config.get("LOCAL_STORAGE_PATH"),
        )
    return StorageService()
