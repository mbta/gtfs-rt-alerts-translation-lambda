from typing import Any

import pytest
from google.transit import gtfs_realtime_pb2

from gtfs_translation.core.processor import FeedProcessor
from gtfs_translation.core.translator import MockTranslator


@pytest.mark.asyncio
async def test_process_feed_new_translations() -> None:
    # Setup Feed
    feed = gtfs_realtime_pb2.FeedMessage()
    entity = feed.entity.add()
    entity.id = "alert1"
    alert = entity.alert

    # Header
    h = alert.header_text.translation.add()
    h.text = "Subway Delay"
    h.language = "en"

    # URL
    u = alert.url.translation.add()
    u.text = "http://mbta.com"
    u.language = "en"

    translator = MockTranslator()

    await FeedProcessor.process_feed(feed, None, translator, ["es", "fr"])

    # Verify Header
    assert len(alert.header_text.translation) == 3
    trans_map = {t.language: t.text for t in alert.header_text.translation}
    assert trans_map["en"] == "Subway Delay"
    assert trans_map["es"] == "[es] Subway Delay"
    assert trans_map["fr"] == "[fr] Subway Delay"

    # Verify URL
    assert len(alert.url.translation) == 3
    url_map = {t.language: t.text for t in alert.url.translation}
    assert url_map["es"] == "http://mbta.com?locale=es"


@pytest.mark.asyncio
async def test_process_feed_diff_logic_reuse() -> None:
    # Old Feed (Has 'Real' translation)
    old_feed = gtfs_realtime_pb2.FeedMessage()
    e_old = old_feed.entity.add()
    e_old.id = "alert-old"
    e_old.alert.header_text.translation.add(text="Delay", language="en")
    e_old.alert.header_text.translation.add(text="Retraso Real", language="es")

    # New Feed (Same English text, different alert ID)
    new_feed = gtfs_realtime_pb2.FeedMessage()
    e_new = new_feed.entity.add()
    e_new.id = "alert-new"
    e_new.alert.header_text.translation.add(text="Delay", language="en")

    translator = MockTranslator()  # Mock would produce "[es] Delay"

    await FeedProcessor.process_feed(new_feed, old_feed, translator, ["es"])

    # Should REUSE "Retraso Real"
    trans = new_feed.entity[0].alert.header_text.translation
    es_text = next(t.text for t in trans if t.language == "es")
    assert es_text == "Retraso Real"


@pytest.mark.asyncio
async def test_process_feed_diff_logic_change() -> None:
    # Old Feed (Different English text)
    old_feed = gtfs_realtime_pb2.FeedMessage()
    e_old = old_feed.entity.add()
    e_old.id = "alert1"
    e_old.alert.header_text.translation.add(text="Old Delay", language="en")
    e_old.alert.header_text.translation.add(text="Retraso Antiguo", language="es")

    # New Feed (New English text)
    new_feed = gtfs_realtime_pb2.FeedMessage()
    e_new = new_feed.entity.add()
    e_new.id = "alert1"
    e_new.alert.header_text.translation.add(text="New Delay", language="en")

    translator = MockTranslator()

    await FeedProcessor.process_feed(new_feed, old_feed, translator, ["es"])

    # Should use NEW translation from MockTranslator
    trans = new_feed.entity[0].alert.header_text.translation
    es_text = next(t.text for t in trans if t.language == "es")
    assert es_text == "[es] New Delay"


@pytest.mark.asyncio
async def test_process_url_existing_locale() -> None:
    # Setup Feed
    feed = gtfs_realtime_pb2.FeedMessage()
    entity = feed.entity.add()
    entity.id = "alert1"

    # URL with existing locale
    u = entity.alert.url.translation.add()
    u.text = "http://mbta.com?locale=en"
    u.language = "en"

    translator = MockTranslator()

    await FeedProcessor.process_feed(feed, None, translator, ["es"])

    # Verify URL: Should just copy the English URL
    url_trans = entity.alert.url.translation
    assert len(url_trans) == 2
    es_url = next(t.text for t in url_trans if t.language == "es")
    assert es_url == "http://mbta.com?locale=en"


@pytest.mark.asyncio
async def test_process_feed_empty_strings() -> None:
    # Setup Feed
    feed = gtfs_realtime_pb2.FeedMessage()
    entity = feed.entity.add()
    entity.id = "alert1"
    alert = entity.alert

    # Empty description
    d = alert.description_text.translation.add()
    d.text = ""
    d.language = "en"

    # Whitespace-only header
    h = alert.header_text.translation.add()
    h.text = "   "
    h.language = "en"

    translator = MockTranslator()

    await FeedProcessor.process_feed(feed, None, translator, ["es"])

    # Verify Description: empty translation is allowed
    desc_trans = alert.description_text.translation
    assert len(desc_trans) == 2
    es_desc = next(t.text for t in desc_trans if t.language == "es")
    assert es_desc == ""

    # Verify Header: empty translation is allowed
    header_trans = alert.header_text.translation
    assert len(header_trans) == 2
    es_header = next(t.text for t in header_trans if t.language == "es")
    assert es_header == ""


@pytest.mark.asyncio
async def test_process_feed_reuse_enhanced_json_translations() -> None:
    old_feed = gtfs_realtime_pb2.FeedMessage()
    new_feed = gtfs_realtime_pb2.FeedMessage()

    dest_json: dict[str, Any] = {
        "entity": [
            {
                "id": "alert1",
                "alert": {
                    "service_effect_text": {
                        "translation": [
                            {"language": "en", "text": "ongoing"},
                            {"language": "es", "text": "en curso"},
                        ]
                    }
                },
            }
        ]
    }

    source_json: dict[str, Any] = {
        "entity": [
            {
                "id": "alert1",
                "alert": {
                    "service_effect_text": {"translation": [{"language": "en", "text": "ongoing"}]}
                },
            }
        ]
    }

    translator = MockTranslator()

    await FeedProcessor.process_feed(
        new_feed,
        old_feed,
        translator,
        ["es"],
        source_json=source_json,
        dest_json=dest_json,
    )

    entity_list = source_json.get("entity", [])
    if isinstance(entity_list, list) and len(entity_list) > 0:
        translations = (
            entity_list[0].get("alert", {}).get("service_effect_text", {}).get("translation", [])
        )
        if isinstance(translations, list):
            es_text = next(t["text"] for t in translations if t["language"] == "es")
            assert es_text == "en curso"


@pytest.mark.asyncio
async def test_process_feed_always_translate_all() -> None:
    # Old Feed (Has 'Real' translation)
    old_feed = gtfs_realtime_pb2.FeedMessage()
    e_old = old_feed.entity.add()
    e_old.id = "alert1"
    e_old.alert.header_text.translation.add(text="Delay", language="en")
    e_old.alert.header_text.translation.add(text="Retraso Real", language="es")

    # New Feed (Same English text, plus another alert missing translations)
    new_feed = gtfs_realtime_pb2.FeedMessage()
    e_new = new_feed.entity.add()
    e_new.id = "alert1"
    e_new.alert.header_text.translation.add(text="Delay", language="en")

    e_new_two = new_feed.entity.add()
    e_new_two.id = "alert2"
    e_new_two.alert.header_text.translation.add(text="New Delay", language="en")

    translator = MockTranslator()
    translator.always_translate_all = True

    await FeedProcessor.process_feed(new_feed, old_feed, translator, ["es"])

    # Because at least one string needs translation, always_translate_all
    # should force re-translation for all strings.
    trans_one = new_feed.entity[0].alert.header_text.translation
    es_text_one = next(t.text for t in trans_one if t.language == "es")
    assert es_text_one == "[es] Delay"

    trans_two = new_feed.entity[1].alert.header_text.translation
    es_text_two = next(t.text for t in trans_two if t.language == "es")
    assert es_text_two == "[es] New Delay"


@pytest.mark.asyncio
async def test_process_feed_always_translate_all_no_missing_strings() -> None:
    old_feed = gtfs_realtime_pb2.FeedMessage()
    e_old = old_feed.entity.add()
    e_old.id = "alert1"
    e_old.alert.header_text.translation.add(text="Delay", language="en")
    e_old.alert.header_text.translation.add(text="Retraso Real", language="es")

    new_feed = gtfs_realtime_pb2.FeedMessage()
    e_new = new_feed.entity.add()
    e_new.id = "alert1"
    e_new.alert.header_text.translation.add(text="Delay", language="en")

    translator = MockTranslator()
    translator.always_translate_all = True

    await FeedProcessor.process_feed(new_feed, old_feed, translator, ["es"])

    trans = new_feed.entity[0].alert.header_text.translation
    es_text = next(t.text for t in trans if t.language == "es")
    assert es_text == "Retraso Real"


@pytest.mark.asyncio
async def test_strip_whitespace_before_translation() -> None:
    """Test that leading/trailing whitespace is stripped before translation."""
    # Setup Feed with text that has leading/trailing whitespace
    feed = gtfs_realtime_pb2.FeedMessage()
    entity = feed.entity.add()
    entity.id = "alert1"
    alert = entity.alert

    # Header with leading/trailing whitespace
    h = alert.header_text.translation.add()
    h.text = "  Subway Delay  "
    h.language = "en"

    # Description with tab and newline
    d = alert.description_text.translation.add()
    d.text = "\tService disruption\n"
    d.language = "en"

    translator = MockTranslator()

    await FeedProcessor.process_feed(feed, None, translator, ["es"])

    # Verify Header: should be translated without whitespace
    header_trans = alert.header_text.translation
    es_header = next(t.text for t in header_trans if t.language == "es")
    assert es_header == "[es] Subway Delay"

    # Verify Description: should be translated without whitespace
    desc_trans = alert.description_text.translation
    es_desc = next(t.text for t in desc_trans if t.language == "es")
    assert es_desc == "[es] Service disruption"


def test_serialize_preserves_numeric_types() -> None:
    """Test that numeric types are preserved in JSON serialization."""
    import json

    # Original JSON with numeric types
    original_json: dict[str, Any] = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": 1700000000,
        },
        "entity": [
            {
                "id": "alert1",
                "alert": {
                    "active_period": [
                        {
                            "start": 1700000000,
                            "end": 1700001000,
                        }
                    ],
                    "informed_entity": [
                        {
                            "route_type": 3,
                            "direction_id": 0,
                        }
                    ],
                    "header_text": {"translation": [{"text": "Test", "language": "en"}]},
                },
            }
        ],
    }

    # Parse the original JSON into protobuf
    feed = FeedProcessor.parse(json.dumps(original_json).encode("utf-8"), "json")

    # Serialize back to JSON
    output_bytes = FeedProcessor.serialize(feed, "json", original_json=original_json)
    output_json = json.loads(output_bytes.decode("utf-8"))

    # Check that numeric types are preserved
    assert isinstance(output_json["header"]["timestamp"], int), (
        f"timestamp should be int, got {type(output_json['header']['timestamp'])}"
    )

    active_period = output_json["entity"][0]["alert"]["active_period"][0]
    assert isinstance(active_period["start"], int), (
        f"active_period.start should be int, got {type(active_period['start'])}"
    )
    assert isinstance(active_period["end"], int), (
        f"active_period.end should be int, got {type(active_period['end'])}"
    )

    informed_entity = output_json["entity"][0]["alert"]["informed_entity"][0]
    assert isinstance(informed_entity["route_type"], int), (
        f"route_type should be int, got {type(informed_entity['route_type'])}"
    )
    assert isinstance(informed_entity["direction_id"], int), (
        f"direction_id should be int, got {type(informed_entity['direction_id'])}"
    )


@pytest.mark.asyncio
async def test_strip_whitespace_reuse_translations() -> None:
    """Test that whitespace doesn't prevent translation reuse."""
    # Old Feed (Has translation for trimmed text)
    old_feed = gtfs_realtime_pb2.FeedMessage()
    e_old = old_feed.entity.add()
    e_old.id = "alert-old"
    e_old.alert.header_text.translation.add(text="Delay", language="en")
    e_old.alert.header_text.translation.add(text="Retraso Real", language="es")

    # New Feed (Same text but with whitespace)
    new_feed = gtfs_realtime_pb2.FeedMessage()
    e_new = new_feed.entity.add()
    e_new.id = "alert-new"
    e_new.alert.header_text.translation.add(text="  Delay  ", language="en")

    translator = MockTranslator()

    await FeedProcessor.process_feed(new_feed, old_feed, translator, ["es"])

    # Should REUSE "Retraso Real" even though new text has whitespace
    trans = new_feed.entity[0].alert.header_text.translation
    es_text = next(t.text for t in trans if t.language == "es")
    assert es_text == "Retraso Real"


def test_serialize_preserves_informed_entity_fields() -> None:
    """Test that all fields in informed_entity are preserved with correct types."""
    import json

    # Original JSON with all possible informed_entity fields
    original_json: dict[str, Any] = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": 1700000000,
        },
        "entity": [
            {
                "id": "alert1",
                "alert": {
                    "informed_entity": [
                        {
                            "stop_id": "NEC-1851-03",
                            "route_id": "CR-Providence",
                            "route_type": 2,
                            "agency_id": "1",
                            "direction_id": 0,
                            "activities": ["BOARD"],
                        },
                        {
                            "stop_id": "FR-0253-02",
                            "route_id": "CR-Fitchburg",
                            "route_type": 2,
                            "activities": ["USING_WHEELCHAIR", "EXITING"],
                            "facility_id": "705",
                        },
                    ],
                    "header_text": {"translation": [{"text": "Test", "language": "en"}]},
                },
            }
        ],
    }

    # Parse the original JSON into protobuf
    feed = FeedProcessor.parse(json.dumps(original_json).encode("utf-8"), "json")

    # Serialize back to JSON (use enhanced=True to preserve activities, facility_id, etc.)
    output_bytes = FeedProcessor.serialize(feed, "json", original_json=original_json, enhanced=True)
    output_json = json.loads(output_bytes.decode("utf-8"))

    # Verify every key exists and types match for each informed_entity
    orig_entities = original_json["entity"][0]["alert"]["informed_entity"]
    output_entities = output_json["entity"][0]["alert"]["informed_entity"]

    assert len(output_entities) == len(orig_entities), (
        f"informed_entity count mismatch: expected {len(orig_entities)}, got {len(output_entities)}"
    )

    for i, (orig_ie, output_ie) in enumerate(zip(orig_entities, output_entities, strict=True)):
        for key, orig_value in orig_ie.items():
            assert key in output_ie, (
                f"informed_entity[{i}] missing key '{key}': expected {orig_ie}, got {output_ie}"
            )
            output_value = output_ie[key]
            assert output_value == orig_value, (
                f"informed_entity[{i}]['{key}'] value mismatch: "
                f"expected {orig_value!r}, got {output_value!r}"
            )
            assert type(output_value) is type(orig_value), (
                f"informed_entity[{i}]['{key}'] type mismatch: "
                f"expected {type(orig_value).__name__}, got {type(output_value).__name__}"
            )


def test_serialize_standard_json_excludes_enhanced_fields() -> None:
    """Test that standard JSON output (enhanced=False) excludes non-Protobuf fields."""
    import json

    # Original JSON with enhanced fields that aren't in the Protobuf spec
    original_json: dict[str, Any] = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": 1700000000,
        },
        "entity": [
            {
                "id": "alert1",
                "alert": {
                    "effect_detail": "SNOW",  # Enhanced field
                    "informed_entity": [
                        {
                            "stop_id": "NEC-1851-03",
                            "route_id": "CR-Providence",
                            "route_type": 2,
                            "activities": ["BOARD"],  # Enhanced field
                            "facility_id": "705",  # Enhanced field
                        },
                    ],
                    "service_effect_text": {  # Enhanced field
                        "translation": [{"text": "Ongoing", "language": "en"}]
                    },
                    "timeframe_text": {  # Enhanced field
                        "translation": [{"text": "Now", "language": "en"}]
                    },
                    "header_text": {"translation": [{"text": "Test", "language": "en"}]},
                },
            }
        ],
    }

    # Parse the original JSON into protobuf
    feed = FeedProcessor.parse(json.dumps(original_json).encode("utf-8"), "json")

    # Serialize back to standard JSON (enhanced=False, the default)
    output_bytes = FeedProcessor.serialize(feed, "json", original_json=original_json)
    output_json = json.loads(output_bytes.decode("utf-8"))

    alert = output_json["entity"][0]["alert"]
    informed_entity = alert["informed_entity"][0]

    # MBTA-specific enhanced fields should NOT be present in standard JSON
    assert "service_effect_text" not in alert, "service_effect_text should not be in standard JSON"
    assert "timeframe_text" not in alert, "timeframe_text should not be in standard JSON"
    assert "activities" not in informed_entity, "activities should not be in standard JSON"
    assert "facility_id" not in informed_entity, "facility_id should not be in standard JSON"

    # Experimental GTFS-RT fields (cause_detail, effect_detail) SHOULD be present
    # These are part of the spec, just not in our protobuf bindings
    assert alert["effect_detail"] == "SNOW", "effect_detail should be preserved in standard JSON"

    # Standard Protobuf fields should still be present
    assert "header_text" in alert
    assert informed_entity["stop_id"] == "NEC-1851-03"
    assert informed_entity["route_id"] == "CR-Providence"
    assert informed_entity["route_type"] == 2
