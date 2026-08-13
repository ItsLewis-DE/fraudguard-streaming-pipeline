"""Read and write immutable ML artifacts in S3-compatible object storage.

Flow:
    1. Parse a strict ``s3://bucket/key`` destination.
    2. Hash the local file and inspect any existing object's SHA-256 metadata.
    3. Reuse an identical object or reject a conflicting overwrite.
    4. Upload a new object and verify its recorded hash before returning success.

The same API works with AWS S3 and MinIO through a configurable endpoint.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from fraudguard_ml.artifacts import ArtifactError, sha256_file


@dataclass(frozen=True)
class S3Location:
    """Validated bucket/key representation of an S3 URI."""

    bucket: str
    key: str

    @classmethod
    def parse(cls, uri: str) -> Self:
        """Parse a non-empty object URI and reject other URI schemes."""

        parsed = urlparse(uri)
        if parsed.schema != "s3" or not parsed.netloc or not parsed.path.strip("/"):
            raise ValueError("S3 URI must be s3://bucket/key")
        return cls(bucket=parsed.netloc, key=parsed.path.lstrip("/"))


@dataclass(frozen=True)
class ObjectStorageSettings:
    """Credentials and endpoint settings for an S3-compatible service."""

    endpoint_url: str
    access_key: str
    secret_key: str
    region_name: str = "us-east-1"

    @classmethod
    def from_env(cls) -> "ObjectStorageSettings":
        """Load MinIO/S3 settings from the pipeline environment."""

        access_key = os.getenv("MINIO_ACCESS_KEY") or os.getenv("MINIO_AIRFLOW_USER")
        secret_key = os.getenv("MINIO_SECRET_KEY") or os.getenv(
            "MINIO_AIRFLOW_PASSWORD"
        )
        if not access_key or not secret_key:
            raise ValueError("MinIO credentials must be configured")
        return cls(
            endpoint_url=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
            access_key=access_key,
            secret_key=secret_key,
        )


def create_s3_client(settings: ObjectStorageSettings) -> BaseClient:
    """Create a boto3 S3 client from validated object-storage settings."""

    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        region_name=settings.region_name,
    )


def object_sha256(client: BaseClient, location: S3Location) -> str | None:
    """Return an object's SHA-256 metadata, or ``None`` when it does not exist.

    An empty string means that the object exists but lacks trusted hash metadata,
    which intentionally differs from a missing object.
    """

    try:
        response = client.head_object(Bucket=location.bucket, Key=location.key)
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status == 404:
            return None
        raise ArtifactError(
            f"cannot inspect object: s3://{location.bucket}/{location.key}"
        ) from exc
    metadata = response.get("Metadata", {})
    value = metadata.get("sha256")
    return str(value) if value else ""


def upload_file_immutable(client: BaseClient, source: Path, uri: str) -> str:
    """Upload once and prove that the remote object's hash matches the source.

    Repeating the call is idempotent only when the destination already records
    the same SHA-256. A different or missing hash is treated as a conflict.
    """

    location = S3Location.parse(uri)
    local_sha256 = sha256_file(source)
    existing_sha256 = object_sha256(client, location)
    if existing_sha256 is not None:
        if existing_sha256 == local_sha256:
            return local_sha256
        raise ArtifactError(f"refusing to overwrite immutable object: {uri}")
    try:
        client.upload_file(
            str(source),
            location.bucket,
            location.key,
            ExtraArgs={"Metadata": {"sha256": local_sha256}},
        )
    except ClientError as exc:
        raise ArtifactError(f"cannot upload object: {uri}") from exc
    remote_sha256 = object_sha256(client, location)
    if remote_sha256 != local_sha256:
        raise ArtifactError(f"object hash verification failed: {uri}")
    return local_sha256


def download_file(client: BaseClient, uri: str, destination: Path) -> None:
    """Download one object, creating the local parent directory when necessary."""

    location = S3Location.parse(uri)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        client.download_file(location.bucket, location.key, str(destination))
        # Khi download phai chuyen destination sang str
    except ClientError as exc:
        raise ArtifactError(f"cannot download object: {uri}") from exc
