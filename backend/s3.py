"""
S3 utilities for CallRadar.

Provides upload, presigned URL generation, and metadata fetch helpers.
All operations use the S3_BUCKET_NAME env var (loaded via secrets.py).
"""

from __future__ import annotations

import io
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _client():
    """Return a boto3 S3 client."""
    import boto3
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-south-1"))


def _bucket() -> str:
    """Return the configured S3 bucket name."""
    name = os.environ.get("S3_BUCKET_NAME")
    if not name:
        raise RuntimeError("S3_BUCKET_NAME is not set in the environment")
    return name


def upload_bytes(data: bytes, key: str, content_type: str = "audio/mpeg") -> str:
    """Upload raw bytes to S3 under the given key.

    Args:
        data: Raw bytes to upload.
        key: S3 object key (e.g. 'audio/12345.mp3').
        content_type: MIME type for the object.

    Returns:
        The S3 key that was written.
    """
    _client().upload_fileobj(
        io.BytesIO(data),
        _bucket(),
        key,
        ExtraArgs={"ContentType": content_type},
    )
    logger.info("s3: uploaded %d bytes → s3://%s/%s", len(data), _bucket(), key)
    return key


def presigned_url(key: str, expires: int = 3600) -> str:
    """Return a presigned GET URL for an S3 key.

    Args:
        key: S3 object key.
        expires: URL lifetime in seconds (default 1 hour).

    Returns:
        HTTPS presigned URL string.
    """
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=expires,
    )


def get_json(key: str) -> dict[str, Any] | None:
    """Fetch a JSON object from S3.

    Args:
        key: S3 object key pointing to a JSON file.

    Returns:
        Parsed dict, or None if the key does not exist.
    """
    try:
        obj = _client().get_object(Bucket=_bucket(), Key=key)
        return json.loads(obj["Body"].read())
    except Exception as exc:
        logger.debug("s3.get_json(%s) failed: %s", key, exc)
        return None


def audio_key(call_id: str) -> str:
    """Return the canonical S3 key for a call's audio file."""
    return f"audio/{call_id}.mp3"


def metadata_key(call_id: str) -> str:
    """Return the canonical S3 key for a call's metadata JSON."""
    return f"metadata/{call_id}.json"
