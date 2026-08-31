"""
AWS Parameter Store bootstrap.

Fetches all /callradar/* parameters and injects them into os.environ
before any engine or DB code reads environment variables.

Falls back silently when AWS credentials are absent so local dev
with a plain .env file continues to work unchanged.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def load_secrets() -> None:
    """Fetch /callradar/* parameters from AWS SSM Parameter Store and inject into os.environ.

    Only sets a variable if it is not already present — docker-compose
    environment overrides (e.g. DATABASE_URL) are never clobbered.
    Exits silently when boto3 is missing or AWS credentials are unavailable.
    """
    # Load .env first so local dev and judge setups work without manual exports
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)  # never overrides already-set env vars
    except ImportError:
        pass

    has_explicit_creds = bool(os.environ.get("AWS_ACCESS_KEY_ID"))
    on_ec2 = _running_on_ec2()

    if not has_explicit_creds and not on_ec2:
        logger.debug("secrets: no AWS credentials found — skipping Parameter Store")
        return

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.warning("secrets: boto3 not installed — skipping Parameter Store")
        return

    region = os.environ.get("AWS_REGION", "ap-south-1")

    try:
        ssm = boto3.client("ssm", region_name=region)
        response = ssm.get_parameters_by_path(
            Path="/callradar/",
            Recursive=True,
            WithDecryption=True,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning("secrets: Parameter Store fetch failed — %s", exc)
        return

    loaded: list[str] = []
    for param in response.get("Parameters", []):
        env_key = param["Name"].split("/")[-1]
        if not os.environ.get(env_key):
            os.environ[env_key] = param["Value"]
            loaded.append(env_key)

    if loaded:
        logger.info("secrets: loaded from Parameter Store — %s", ", ".join(loaded))
    else:
        logger.debug("secrets: all parameters already set in environment")


def _running_on_ec2() -> bool:
    """Return True when the instance metadata service is reachable (EC2 / ECS with IAM role)."""
    try:
        import urllib.request
        urllib.request.urlopen(
            "http://169.254.169.254/latest/meta-data/", timeout=0.3
        )
        return True
    except Exception:
        return False
