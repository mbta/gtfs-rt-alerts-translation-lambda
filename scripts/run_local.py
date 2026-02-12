import asyncio
import logging
import os
import sys

# Add the project root to sys.path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import argparse

from gtfs_translation.config import settings
from gtfs_translation.core.processor import FeedFormat, FeedProcessor
from gtfs_translation.core.smartling import (
    SmartlingFileTranslator,
    SmartlingJobBatchesTranslator,
    SmartlingTranslator,
)


async def run_local(source_url: str, target_langs: list[str]) -> None:
    # 1. Fetch source (minimal version for CLI)
    from gtfs_translation.core.fetcher import fetch_source

    content: bytes
    fmt: FeedFormat

    if source_url.startswith("s3://") or source_url.startswith("http"):
        content, fmt = await fetch_source(source_url)
    else:
        with open(source_url, "rb") as f:
            content = f.read()
        fmt = "json" if source_url.endswith(".json") else "pb"

    new_feed = FeedProcessor.parse(content, fmt)

    original_json = None
    if fmt == "json":
        import json

        original_json = json.loads(content.decode("utf-8"))

    # 2. Translate (no old feed/caching for local test run usually)
    translator: SmartlingTranslator
    if settings.smartling_project_id:
        translator = SmartlingJobBatchesTranslator(
            settings.smartling_user_id,
            settings.smartling_user_secret,
            settings.smartling_project_id,
            source_url,
            job_name_template=settings.smartling_job_name_template,
        )
    else:
        translator = SmartlingFileTranslator(
            settings.smartling_user_id,
            settings.smartling_user_secret,
            settings.smartling_account_uid,
        )

    try:
        metrics = await FeedProcessor.process_feed(
            new_feed,
            None,
            translator,
            target_langs,
            concurrency_limit=settings.concurrency_limit,
            source_json=original_json,
        )

        # 3. Serialize and print to stdout
        output = FeedProcessor.serialize(new_feed, "json", original_json=original_json)
        print(output.decode("utf-8"))

        # Print metrics to stderr so they don't mess up piped JSON
        print(f"Metrics: {metrics.to_dict()}", file=sys.stderr)

    finally:
        await translator.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_url", help="URL or local path to GTFS feed")
    parser.add_argument("--langs", default="es-LA", help="Comma-separated target languages")
    args = parser.parse_args()

    # Configure logging to stderr
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    langs = [lang.strip() for lang in args.langs.split(",")]

    # We need settings for Smartling, but we can override source/dest if needed
    # Settings are already loaded from env

    asyncio.run(run_local(args.source_url, langs))
