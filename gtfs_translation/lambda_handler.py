import asyncio
import logging
from typing import Any
from urllib.parse import unquote_plus

import boto3

from gtfs_translation.config import settings
from gtfs_translation.core.fetcher import (
    fetch_old_feed,
    fetch_source,
    get_s3_parts,
    resolve_secrets,
)
from gtfs_translation.core.processor import FeedFormat, FeedProcessor, ProcessingMetrics
from gtfs_translation.core.smartling import (
    SmartlingJobBatchesTranslator,
    SmartlingTranslator,
)
from gtfs_translation.proto import gtfs_realtime_pb2

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


def _apply_fallback_translations(
    new_feed: gtfs_realtime_pb2.FeedMessage,
    old_feed: gtfs_realtime_pb2.FeedMessage | None,
    target_langs: list[str],
    source_json: dict[str, Any] | None,
    dest_json: dict[str, Any] | None,
) -> None:
    """Apply cached translations from old feed as a fallback when translation fails."""
    cached_count = FeedProcessor.apply_cached_translations(
        new_feed,
        old_feed,
        target_langs,
        source_json=source_json,
        dest_json=dest_json,
    )
    logger.log(
        NOTICE_LEVEL,
        "Applied %d cached translations from previous feed.",
        cached_count,
    )


async def run_translation(source_url: str, dest_urls: list[str]) -> None:
    if not dest_urls:
        raise ValueError("No destination URLs provided")

    if any(source_url == d for d in dest_urls):
        raise ValueError(f"Source URL matches one of the destinations: {source_url}")

    # 1. Fetch source
    content, source_fmt = await fetch_source(source_url)
    new_feed = FeedProcessor.parse(content, source_fmt)

    # We keep the original JSON for merging back non-standard fields during serialization
    source_json = None
    if source_fmt == "json":
        import json

        source_json = json.loads(content.decode("utf-8"))

    # 2. Pick reference destination for diffing
    # Prefer JSON format to preserve enhanced fields context for translation reuse
    ref_dest_url = dest_urls[0]
    for d in dest_urls:
        if d.endswith(".json"):
            ref_dest_url = d
            break

    ref_fmt: FeedFormat = "json" if ref_dest_url.endswith(".json") else "pb"
    logger.log(NOTICE_LEVEL, "Using reference destination: %s (%s)", ref_dest_url, ref_fmt)

    # Fetch old feed from reference
    old_feed, dest_json = await fetch_old_feed(ref_dest_url, ref_fmt)

    # 3. Translate
    translator: SmartlingTranslator
    if settings.smartling_project_id:
        translator = SmartlingJobBatchesTranslator(
            settings.smartling_user_id,
            settings.smartling_user_secret,
            settings.smartling_project_id,
            source_url,
            job_name_template=settings.smartling_job_name_template,
        )
        logger.log(NOTICE_LEVEL, "Using Smartling Job Batches translator")
    else:
        translator = SmartlingTranslator(
            settings.smartling_user_id,
            settings.smartling_user_secret,
            settings.smartling_account_uid,
        )
        logger.log(NOTICE_LEVEL, "Using Smartling MT Router translator")

    try:
        translation_successful = True
        metrics = None
        try:
            # Enforce translation timeout to ensure feed is always published
            metrics = await asyncio.wait_for(
                FeedProcessor.process_feed(
                    new_feed,
                    old_feed,
                    translator,
                    settings.target_lang_list,
                    concurrency_limit=settings.concurrency_limit,
                    source_json=source_json,
                    dest_json=dest_json,
                ),
                timeout=settings.translation_timeout,
            )
            logger.log(NOTICE_LEVEL, "Translation metrics: %s", metrics.to_dict())
        except TimeoutError:
            logger.warning(
                "Translation timed out after %s seconds. "
                "Applying cached translations from previous feed.",
                settings.translation_timeout,
            )
            _apply_fallback_translations(
                new_feed, old_feed, settings.target_lang_list, source_json, dest_json
            )
            translation_successful = False
            metrics = None
        except Exception as e:
            logger.exception(
                "Translation failed with error: %s. "
                "Applying cached translations from previous feed.",
                e,
            )
            _apply_fallback_translations(
                new_feed, old_feed, settings.target_lang_list, source_json, dest_json
            )
            translation_successful = False
            metrics = None

        if not translation_successful or not should_upload(old_feed, new_feed, metrics):
            if not translation_successful:
                # Always upload if translation failed/timed out (with cached translations applied)
                logger.log(
                    NOTICE_LEVEL,
                    "Uploading feed with cached translations due to translation failure.",
                )
            else:
                logger.log(NOTICE_LEVEL, "No translation changes detected; skipping upload.")
                return

        # 4. Upload to all destinations
        for dest_url in dest_urls:
            dest_fmt: FeedFormat = "json" if dest_url.endswith(".json") else "pb"
            # Only output enhanced fields for URLs containing "enhanced"
            enhanced = "enhanced" in dest_url.lower()
            translated_content = FeedProcessor.serialize(
                new_feed, dest_fmt, original_json=source_json, enhanced=enhanced
            )
            bucket, key = get_s3_parts(dest_url)
            content_type = "application/json" if dest_fmt == "json" else "application/x-protobuf"
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=translated_content,
                ContentType=content_type,
            )
            logger.log(NOTICE_LEVEL, "Uploaded to %s", dest_url)

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

    dest_urls = settings.destination_bucket_url_list
    if not dest_urls:
        raise ValueError("DESTINATION_BUCKET_URLS must be configured")

    asyncio.run(run_translation(source_url, dest_urls))

    return {"statusCode": 200, "body": "Translation completed"}
