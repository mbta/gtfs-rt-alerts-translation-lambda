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
    e_old.id = "alert1"
    e_old.alert.header_text.translation.add(text="Delay", language="en")
    e_old.alert.header_text.translation.add(text="Retraso Real", language="es")

    # New Feed (Same English text)
    new_feed = gtfs_realtime_pb2.FeedMessage()
    e_new = new_feed.entity.add()
    e_new.id = "alert1"
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
