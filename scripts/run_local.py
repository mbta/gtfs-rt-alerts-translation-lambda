import os
import sys

# Add the project root to sys.path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import argparse
import asyncio

from gtfs_translation.config import settings
from gtfs_translation.core.processor import FeedFormat, FeedProcessor
from gtfs_translation.core.smartling import SmartlingTranslator


def run_local(source_url: str, target_langs: list[str]) -> None:
    # 1. Fetch source (minimal version for CLI)
    import boto3
    import httpx

    content: bytes
    fmt: FeedFormat = "json" if source_url.endswith(".json") else "pb"

    if source_url.startswith("s3://"):
        bucket, key = source_url[5:].split("/", 1)
        s3 = boto3.client("s3")
        resp = s3.get_object(Bucket=bucket, Key=key)
        content = resp["Body"].read()
    elif source_url.startswith("http"):
        with httpx.Client() as client:
            resp_http = client.get(source_url)
            resp_http.raise_for_status()
            content = resp_http.content
    else:
        with open(source_url, "rb") as f:
            content = f.read()

    new_feed = FeedProcessor.parse(content, fmt)

    original_json = None
    if fmt == "json":
        import json

        original_json = json.loads(content.decode("utf-8"))

    # 2. Translate (no old feed/caching for local test run usually)
    translator = SmartlingTranslator(
        settings.smartling_user_id, settings.smartling_user_secret, settings.smartling_account_uid
    )

    try:
        metrics = FeedProcessor.process_feed(
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
        translator.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_url", help="URL or local path to GTFS feed")
    parser.add_argument("--langs", default="es", help="Comma-separated target languages")
    args = parser.parse_args()

    langs = [lang.strip() for lang in args.langs.split(",")]

    # We need settings for Smartling, but we can override source/dest if needed
    # Settings are already loaded from env

    run_local(args.source_url, langs)
