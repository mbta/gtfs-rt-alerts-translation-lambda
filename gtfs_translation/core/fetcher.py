import logging

import boto3
import botocore
import httpx
from google.transit import gtfs_realtime_pb2

from gtfs_translation.config import settings
from gtfs_translation.core.processor import FeedFormat, FeedProcessor

logger = logging.getLogger(__name__)
s3 = boto3.client("s3")
secrets = boto3.client("secretsmanager")


def resolve_secrets() -> None:
    if settings.smartling_user_secret_arn and not settings.smartling_user_secret:
        logger.info(
            "Fetching Smartling secret from Secrets Manager: %s", settings.smartling_user_secret_arn
        )
        resp = secrets.get_secret_value(SecretId=settings.smartling_user_secret_arn)
        settings.smartling_user_secret = resp["SecretString"]


def get_s3_parts(url: str) -> tuple[str, str]:
    if not url.startswith("s3://"):
        raise ValueError(f"Invalid S3 URL: {url}")
    path = url[5:]
    if "/" not in path:
        raise ValueError(f"Invalid S3 URL: {url}")
    bucket, key = path.split("/", 1)
    return bucket, key


async def fetch_source(url: str) -> tuple[bytes, FeedFormat]:
    if url.startswith("s3://"):
        bucket, key = get_s3_parts(url)
        resp = s3.get_object(Bucket=bucket, Key=key)
        content: bytes = resp["Body"].read()
    else:
        async with httpx.AsyncClient() as client:
            resp_http = await client.get(url)
            resp_http.raise_for_status()
            content = resp_http.content

    fmt: FeedFormat = "json" if url.endswith(".json") else "pb"
    return content, fmt


async def fetch_old_feed(dest_url: str, fmt: FeedFormat) -> gtfs_realtime_pb2.FeedMessage | None:
    try:
        bucket, key = get_s3_parts(dest_url)
        resp = s3.get_object(Bucket=bucket, Key=key)
        content: bytes = resp["Body"].read()
        return FeedProcessor.parse(content, fmt)
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404" or e.response["Error"]["Code"] == "NoSuchKey":
            logger.info("Destination feed not found, starting fresh: %s", dest_url)
            return None
        raise e
    except Exception:
        logger.exception("Unexpected error fetching old feed from %s", dest_url)
        return None
