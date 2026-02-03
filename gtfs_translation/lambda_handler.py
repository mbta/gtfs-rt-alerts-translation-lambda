import asyncio
import logging
from typing import Any

import boto3
import botocore
import httpx
from google.transit import gtfs_realtime_pb2

from gtfs_translation.config import settings
from gtfs_translation.core.processor import FeedFormat, FeedProcessor
from gtfs_translation.core.smartling import SmartlingTranslator

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


# Fetch secrets once at module load (startup)
resolve_secrets()


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


async def run_translation(source_url: str, dest_url: str) -> None:
    if source_url == dest_url:
        raise ValueError(f"Source and destination URL are the same: {source_url}")

    # 1. Fetch source
    content, fmt = await fetch_source(source_url)
    new_feed = FeedProcessor.parse(content, fmt)

    # We keep the original JSON for merging back non-standard fields during serialization
    original_json = None
    if fmt == "json":
        import json

        original_json = json.loads(content.decode("utf-8"))

    # 2. Fetch old feed for diffing
    old_feed = await fetch_old_feed(dest_url, fmt)

    # 3. Translate
    translator = SmartlingTranslator(
        settings.smartling_user_id, settings.smartling_user_secret, settings.smartling_account_uid
    )

    try:
        metrics = await FeedProcessor.process_feed(
            new_feed,
            old_feed,
            translator,
            settings.target_lang_list,
            concurrency_limit=settings.concurrency_limit,
            original_json=original_json,
        )

        logger.info("Translation metrics: %s", metrics.to_dict())

        # 4. Upload
        translated_content = FeedProcessor.serialize(new_feed, fmt, original_json=original_json)
        bucket, key = get_s3_parts(dest_url)
        s3.put_object(Bucket=bucket, Key=key, Body=translated_content)

    finally:
        await translator.close()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    # Hybrid Trigger Logic
    source_url = settings.source_url

    # Check if S3 Event
    if "Records" in event:
        record = event["Records"][0]
        if "s3" in record:
            bucket = record["s3"]["bucket"]["name"]
            key = record["s3"]["object"]["key"]
            source_url = f"s3://{bucket}/{key}"

    if not source_url:
        raise ValueError("No source URL provided via environment or event")

    dest_url = settings.destination_bucket_url
    if not dest_url:
        raise ValueError("DESTINATION_BUCKET_URL must be configured")

    asyncio.run(run_translation(source_url, dest_url))

    return {"statusCode": 200, "body": "Translation completed"}
