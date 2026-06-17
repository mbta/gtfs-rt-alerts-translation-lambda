"""Tests for cause_detail and effect_detail field handling.

These experimental GTFS-RT fields should:
1. Not be translated (remain English-only TranslatedString in PB output)
2. Be serialized as raw strings in JSON output (not TranslatedString objects)
"""

import json
from typing import Any

import pytest

from gtfs_translation.core.processor import FeedProcessor
from gtfs_translation.proto import gtfs_realtime_pb2


@pytest.fixture
def feed_with_cause_effect_detail_translated_string_json() -> dict[str, Any]:
    """Source JSON with cause_detail and effect_detail as raw strings (MBTA format)."""
    return {
        "header": {"gtfs_realtime_version": "2.0", "timestamp": 1234567890},
        "entity": [
            {
                "id": "alert1",
                "alert": {
                    "header_text": {"translation": [{"text": "Delay", "language": "en"}]},
                    "cause": "OTHER_CAUSE",
                    "cause_detail": {"translation": [{"text": "CONSTRUCTION", "language": "en"}]},
                    "effect": "SIGNIFICANT_DELAYS",
                    "effect_detail": {"translation": [{"text": "STATION_ISSUE", "language": "en"}]},
                },
            }
        ],
    }


@pytest.fixture
def feed_with_cause_effect_detail_raw_string_json() -> dict[str, Any]:
    """Source JSON with cause_detail and effect_detail as raw strings (MBTA format)."""
    return {
        "header": {"gtfs_realtime_version": "2.0", "timestamp": 1234567890},
        "entity": [
            {
                "id": "alert1",
                "alert": {
                    "header_text": {"translation": [{"text": "Delay", "language": "en"}]},
                    "cause": "OTHER_CAUSE",
                    "cause_detail": "CONSTRUCTION",
                    "effect": "SIGNIFICANT_DELAYS",
                    "effect_detail": "STATION_ISSUE",
                },
            }
        ],
    }


class TestCauseEffectDetailProtobufOutput:
    """Test that cause_detail and effect_detail are TranslatedString with English in PB output."""

    def test_pb_output_has_cause_detail_translated_string_as_translated_string(
        self, feed_with_cause_effect_detail_translated_string_json: dict[str, Any]
    ) -> None:
        """cause_detail should be a TranslatedString with English text in PB output."""
        source_json = feed_with_cause_effect_detail_translated_string_json
        content = json.dumps(source_json).encode("utf-8")

        feed = FeedProcessor.parse(content, "json", original_json=source_json)

        # Serialize to PB and parse back
        pb_output = FeedProcessor.serialize(feed, "pb")
        parsed_feed = gtfs_realtime_pb2.FeedMessage()
        parsed_feed.ParseFromString(pb_output)

        alert = parsed_feed.entity[0].alert
        assert alert.HasField("cause_detail")
        assert len(alert.cause_detail.translation) == 1
        assert alert.cause_detail.translation[0].text == "CONSTRUCTION"
        assert alert.cause_detail.translation[0].language == "en"

    def test_pb_output_has_effect_detail_translated_string_as_translated_string(
        self, feed_with_cause_effect_detail_translated_string_json: dict[str, Any]
    ) -> None:
        """effect_detail should be a TranslatedString with English text in PB output."""
        source_json = feed_with_cause_effect_detail_translated_string_json
        content = json.dumps(source_json).encode("utf-8")

        feed = FeedProcessor.parse(content, "json", original_json=source_json)

        # Serialize to PB and parse back
        pb_output = FeedProcessor.serialize(feed, "pb")
        parsed_feed = gtfs_realtime_pb2.FeedMessage()
        parsed_feed.ParseFromString(pb_output)

        alert = parsed_feed.entity[0].alert
        assert alert.HasField("effect_detail")
        assert len(alert.effect_detail.translation) == 1
        assert alert.effect_detail.translation[0].text == "STATION_ISSUE"
        assert alert.effect_detail.translation[0].language == "en"

    def test_pb_output_has_cause_detail_raw_string_as_translated_string(
        self, feed_with_cause_effect_detail_raw_string_json: dict[str, Any]
    ) -> None:
        """cause_detail should be a TranslatedString with English text in PB output."""
        source_json = feed_with_cause_effect_detail_raw_string_json
        content = json.dumps(source_json).encode("utf-8")

        feed = FeedProcessor.parse(content, "json", original_json=source_json)

        # Serialize to PB and parse back
        pb_output = FeedProcessor.serialize(feed, "pb")
        parsed_feed = gtfs_realtime_pb2.FeedMessage()
        parsed_feed.ParseFromString(pb_output)

        alert = parsed_feed.entity[0].alert
        assert alert.HasField("cause_detail")
        assert len(alert.cause_detail.translation) == 1
        assert alert.cause_detail.translation[0].text == "CONSTRUCTION"
        assert alert.cause_detail.translation[0].language == "en"

    def test_pb_output_has_effect_detail_raw_string_as_translated_string(
        self, feed_with_cause_effect_detail_raw_string_json: dict[str, Any]
    ) -> None:
        """effect_detail should be a TranslatedString with English text in PB output."""
        source_json = feed_with_cause_effect_detail_raw_string_json
        content = json.dumps(source_json).encode("utf-8")

        feed = FeedProcessor.parse(content, "json", original_json=source_json)

        # Serialize to PB and parse back
        pb_output = FeedProcessor.serialize(feed, "pb")
        parsed_feed = gtfs_realtime_pb2.FeedMessage()
        parsed_feed.ParseFromString(pb_output)

        alert = parsed_feed.entity[0].alert
        assert alert.HasField("effect_detail")
        assert len(alert.effect_detail.translation) == 1
        assert alert.effect_detail.translation[0].text == "STATION_ISSUE"
        assert alert.effect_detail.translation[0].language == "en"


class TestCauseEffectDetailNotTranslated:
    """Test that cause_detail and effect_detail are not sent for translation."""

    @pytest.mark.asyncio
    async def test_cause_effect_detail_translated_string_not_extracted_for_translation(
        self, feed_with_cause_effect_detail_translated_string_json: dict[str, Any]
    ) -> None:
        """cause_detail and effect_detail should not be in the translation map."""
        source_json = feed_with_cause_effect_detail_translated_string_json
        content = json.dumps(source_json).encode("utf-8")

        feed = FeedProcessor.parse(content, "json")

        # Gather translations - these fields should NOT be included
        translation_map = FeedProcessor._gather_translations_from_feed(
            feed, source_json, include_all_translations=False
        )

        # Only "Delay" from header_text should be in the map
        assert "Delay" in translation_map
        # The raw string values should NOT be in the map
        assert "CONSTRUCTION" not in translation_map
        assert "STATION_ISSUE" not in translation_map

    @pytest.mark.asyncio
    async def test_cause_effect_detail_raw_string_not_extracted_for_translation(
        self, feed_with_cause_effect_detail_raw_string_json: dict[str, Any]
    ) -> None:
        """cause_detail and effect_detail should not be in the translation map."""
        source_json = feed_with_cause_effect_detail_raw_string_json
        content = json.dumps(source_json).encode("utf-8")

        feed = FeedProcessor.parse(content, "json")

        # Gather translations - these fields should NOT be included
        translation_map = FeedProcessor._gather_translations_from_feed(
            feed, source_json, include_all_translations=False
        )

        # Only "Delay" from header_text should be in the map
        assert "Delay" in translation_map
        # The raw string values should NOT be in the map
        assert "CONSTRUCTION" not in translation_map
        assert "STATION_ISSUE" not in translation_map
