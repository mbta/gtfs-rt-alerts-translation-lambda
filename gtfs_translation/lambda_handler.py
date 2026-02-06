import asyncio
import logging
from typing import Any
from urllib.parse import unquote_plus

import boto3
from google.transit import gtfs_realtime_pb2

from gtfs_translation.config import settings
from gtfs_translation.core.fetcher import (
    fetch_old_feed,
    fetch_source,
    get_s3_parts,
    resolve_secrets,
)
from gtfs_translation.core.processor import FeedProcessor, ProcessingMetrics
from gtfs_translation.core.smartling import SmartlingFileTranslator

NOTICE_LEVEL = 25
logging.addLevelName(NOTICE_LEVEL, "NOTICE")

logger = logging.getLogger(__name__)
s3 = boto3.client("s3")

# Fetch secrets once at module load (startup)
resolve_secrets()


def should_upload(
    old_feed: gtfs_realtime_pb2.FeedMessage | None,
    new_feed: gtfs_realtime_pb2.FeedMessage,
    metrics: ProcessingMetrics | None = None,
) -> bool:
    if not old_feed:
        return True

    if old_feed.header.timestamp != new_feed.header.timestamp:
        return True

    if metrics is None:
        return True

    return metrics.strings_translated > 0


async def run_translation(source_url: str, dest_url: str) -> None:
    if source_url == dest_url:
        raise ValueError(f"Source and destination URL are the same: {source_url}")

    # 1. Fetch source
    content, fmt = await fetch_source(source_url)
    new_feed = FeedProcessor.parse(content, fmt)

    # We keep the original JSON for merging back non-standard fields during serialization
    source_json = None
    if fmt == "json":
        import json

        source_json = json.loads(content.decode("utf-8"))

    # 2. Fetch old feed for diffing
    old_feed, dest_json = await fetch_old_feed(dest_url, fmt)

    # 3. Translate
    translator = SmartlingFileTranslator(
        settings.smartling_user_id, settings.smartling_user_secret, settings.smartling_account_uid
    )

    try:
        metrics = await FeedProcessor.process_feed(
            new_feed,
            old_feed,
            translator,
            settings.target_lang_list,
            concurrency_limit=settings.concurrency_limit,
            source_json=source_json,
            dest_json=dest_json,
        )

        logger.log(NOTICE_LEVEL, "Translation metrics: %s", metrics.to_dict())

        if not should_upload(old_feed, new_feed, metrics):
            logger.log(NOTICE_LEVEL, "No translation changes detected; skipping upload.")
            return

        # 4. Upload
        translated_content = FeedProcessor.serialize(new_feed, fmt, original_json=source_json)
        bucket, key = get_s3_parts(dest_url)
        content_type = "application/json" if fmt == "json" else "application/x-protobuf"
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=translated_content,
            ContentType=content_type,
        )

    finally:
        await translator.close()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())

    # Hybrid Trigger Logic
    source_url = settings.source_url

    # Check if S3 Event
    if "Records" in event:
        record = event["Records"][0]
        if "s3" in record:
            bucket = record["s3"]["bucket"]["name"]
            key = unquote_plus(record["s3"]["object"]["key"])
            source_url = f"s3://{bucket}/{key}"

    if not source_url:
        raise ValueError("No source URL provided via environment or event")

    dest_url = settings.destination_bucket_url
    if not dest_url:
        raise ValueError("DESTINATION_BUCKET_URL must be configured")

    asyncio.run(run_translation(source_url, dest_url))

    return {"statusCode": 200, "body": "Translation completed"}
