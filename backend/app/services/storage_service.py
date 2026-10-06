"""
File storage with pluggable backend.

Closes KI-011: uploads were written to a local path inside the container.
Restarting or replacing the container lost every file, and running more than
one backend replica scattered uploads across machines with no way to find them.

Two backends, selected by configuration:

  - **S3** when AWS_S3_BUCKET is set. Survives container replacement, shared
    across replicas, server-side encrypted.
  - **Local disk** otherwise. Fine for development and single-node demos.

Both implement the same three operations, so calling code does not branch.

## Security notes

Uploads are stored under `uploads/{org_id}/{return_id}/{uuid}_{filename}`. The
org_id prefix means an S3 bucket policy can enforce tenant isolation at the
storage layer as well as the application layer.

Downloads use presigned URLs with a short expiry rather than proxying bytes
through the API. The bucket stays private; links expire; the backend does not
spend memory streaming files.

The stored filename is prefixed with a UUID so a malicious upload cannot
overwrite an existing object by reusing a filename.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    _BOTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BOTO_AVAILABLE = False
    BotoCoreError = ClientError = Exception  # type: ignore

_s3_client = None


def _bucket() -> str:
    return getattr(settings, "AWS_S3_BUCKET", "") or ""


def is_s3_enabled() -> bool:
    return bool(_bucket()) and _BOTO_AVAILABLE


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_REGION", "ap-south-1"),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None) or None,
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None) or None,
        )
    return _s3_client


def _local_root() -> Path:
    root = Path(getattr(settings, "LOCAL_UPLOAD_DIR", "") or "/app/uploads")
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_storage_key(org_id: str, return_id: str, filename: str) -> str:
    """
    org_id first so a bucket policy can scope access per tenant.
    UUID prefix so an upload cannot overwrite an existing object.
    """
    safe = os.path.basename(filename).replace("/", "_").replace("\\", "_")
    return f"uploads/{org_id}/{return_id}/{uuid.uuid4().hex}_{safe}"


def store_file(key: str, content: bytes, content_type: str) -> bool:
    """Persist bytes at `key`. Returns True on success."""
    if is_s3_enabled():
        try:
            _get_s3().put_object(
                Bucket=_bucket(),
                Key=key,
                Body=content,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
            logger.info("Stored s3://%s/%s (%d bytes)", _bucket(), key, len(content))
            return True
        except (BotoCoreError, ClientError) as exc:
            logger.error("S3 upload failed for %s: %s", key, exc)
            return False
        except Exception as exc:  # noqa: BLE001 - deliberate, see below
            # PHASE 7: catch-all for the S3 path.
            #
            # Only boto's own exceptions were caught, so anything else --
            # a DNS failure surfacing as socket.gaierror, an SSL error, a
            # botocore version raising a type boto does not re-export --
            # propagated out of a function whose contract is "returns True
            # on success". The caller in return_mgmt.py checks the return
            # value and raises a clean 500; an escaping exception instead
            # produced an unhandled error with a stack trace, and the
            # upload endpoint could leak infrastructure details.
            #
            # Broad except is normally a smell. Here the contract is
            # explicitly boolean and every failure mode means the same
            # thing to the caller: the bytes are not stored.
            logger.exception("Unexpected error storing %s to S3", key)
            return False

    try:
        path = _local_root() / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        logger.info("Stored %s locally (%d bytes)", key, len(content))
        return True
    except OSError as exc:
        logger.error("Local write failed for %s: %s", key, exc)
        return False
    except Exception:  # noqa: BLE001 - same rationale as the S3 path above
        logger.exception("Unexpected error storing %s locally", key)
        return False


def get_download_url(key: str, expires_seconds: int = 900) -> str | None:
    """
    Presigned S3 URL, or a local API path when S3 is not configured.

    Short expiry (15 min default): long enough for a user to click, short
    enough that a leaked URL in a log or referrer header is not a lasting
    exposure.
    """
    if is_s3_enabled():
        try:
            return _get_s3().generate_presigned_url(
                "get_object",
                Params={"Bucket": _bucket(), "Key": key},
                ExpiresIn=expires_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Presign failed for %s: %s", key, exc)
            return None

    # Local mode: the API serves the bytes, still behind auth.
    return f"/api/v1/files/{key}"


def read_file(key: str) -> bytes | None:
    if is_s3_enabled():
        try:
            obj = _get_s3().get_object(Bucket=_bucket(), Key=key)
            return obj["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            logger.error("S3 read failed for %s: %s", key, exc)
            return None
    try:
        path = _local_root() / key
        return path.read_bytes() if path.exists() else None
    except OSError as exc:
        logger.error("Local read failed for %s: %s", key, exc)
        return None


def delete_file(key: str) -> bool:
    if is_s3_enabled():
        try:
            _get_s3().delete_object(Bucket=_bucket(), Key=key)
            return True
        except (BotoCoreError, ClientError) as exc:
            logger.error("S3 delete failed for %s: %s", key, exc)
            return False
    try:
        path = _local_root() / key
        if path.exists():
            path.unlink()
        return True
    except OSError as exc:
        logger.error("Local delete failed for %s: %s", key, exc)
        return False


def backend_name() -> str:
    if is_s3_enabled():
        return f"s3://{_bucket()}"
    if _bucket() and not _BOTO_AVAILABLE:
        logger.warning("AWS_S3_BUCKET is set but boto3 is not installed - using local disk.")
    return f"local:{_local_root()}"
