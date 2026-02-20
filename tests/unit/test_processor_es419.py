"""Tests for processor with es-419 language code."""

import pytest
from google.transit import gtfs_realtime_pb2

from gtfs_translation.core.processor import FeedProcessor
from gtfs_translation.core.translator import MockTranslator


@pytest.mark.asyncio
async def test_processor_reuses_es419_translations() -> None:
    """Test that translations with es-419 code are properly reused."""
    # Create an old feed with es-419 translations
    old_feed = gtfs_realtime_pb2.FeedMessage()
    old_feed.header.gtfs_realtime_version = "2.0"
    old_feed.header.timestamp = 1000

    entity = old_feed.entity.add()
    entity.id = "alert1"
    alert = entity.alert

    # Add English text
    header_en = alert.header_text.translation.add()
    header_en.text = "Service Alert"
    header_en.language = "en"

    # Add es-419 translation
    header_es = alert.header_text.translation.add()
    header_es.text = "Alerta de Servicio"
    header_es.language = "es-419"

    # Create a new feed with the same English text
    new_feed = gtfs_realtime_pb2.FeedMessage()
    new_feed.header.gtfs_realtime_version = "2.0"
    new_feed.header.timestamp = 2000

    entity = new_feed.entity.add()
    entity.id = "alert1"
    alert = entity.alert

    # Only English text, no translations yet
    header_en = alert.header_text.translation.add()
    header_en.text = "Service Alert"
    header_en.language = "en"

    # Process with MockTranslator
    translator = MockTranslator()
    metrics = await FeedProcessor.process_feed(
        new_feed,
        old_feed,
        translator,
        target_langs=["es-419"],
    )

    # Should reuse the translation, not call translator
    assert metrics.translations_reused == 1
    assert metrics.strings_translated == 0

    # Check that the translation was applied
    alert = new_feed.entity[0].alert
    translations = {t.language: t.text for t in alert.header_text.translation}
    assert "es-419" in translations
    assert translations["es-419"] == "Alerta de Servicio"


@pytest.mark.asyncio
async def test_processor_translates_new_strings_with_es419() -> None:
    """Test that new strings get translated with es-419 code."""
    # Create a new feed with only English
    new_feed = gtfs_realtime_pb2.FeedMessage()
    new_feed.header.gtfs_realtime_version = "2.0"
    new_feed.header.timestamp = 2000

    entity = new_feed.entity.add()
    entity.id = "alert1"
    alert = entity.alert

    header_en = alert.header_text.translation.add()
    header_en.text = "New Alert"
    header_en.language = "en"

    # Process with MockTranslator (no old feed)
    translator = MockTranslator()
    metrics = await FeedProcessor.process_feed(
        new_feed,
        None,
        translator,
        target_langs=["es-419"],
    )

    # Should translate the new string
    assert metrics.translations_reused == 0
    assert metrics.strings_translated == 1

    # Check that the translation was applied with es-419 code
    alert = new_feed.entity[0].alert
    translations = {t.language: t.text for t in alert.header_text.translation}
    assert "es-419" in translations
    # MockTranslator adds [lang] prefix
    assert translations["es-419"] == "[es-419] New Alert"


@pytest.mark.asyncio
async def test_processor_handles_mixed_languages() -> None:
    """Test that processor handles es-419 alongside other languages."""
    # Create a new feed with only English
    new_feed = gtfs_realtime_pb2.FeedMessage()
    new_feed.header.gtfs_realtime_version = "2.0"
    new_feed.header.timestamp = 2000

    entity = new_feed.entity.add()
    entity.id = "alert1"
    alert = entity.alert

    header_en = alert.header_text.translation.add()
    header_en.text = "Alert"
    header_en.language = "en"

    # Process with multiple target languages
    translator = MockTranslator()
    metrics = await FeedProcessor.process_feed(
        new_feed,
        None,
        translator,
        target_langs=["es-419", "fr", "pt"],
    )

    # Should translate for all three languages
    assert metrics.strings_translated == 3

    # Check that all translations were applied
    alert = new_feed.entity[0].alert
    translations = {t.language: t.text for t in alert.header_text.translation}
    assert "es-419" in translations
    assert "fr" in translations
    assert "pt" in translations
    assert translations["es-419"] == "[es-419] Alert"
    assert translations["fr"] == "[fr] Alert"
    assert translations["pt"] == "[pt] Alert"
