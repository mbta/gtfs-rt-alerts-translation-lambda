"""Tests for migrating from es-LA to es-419."""

import pytest
from google.transit import gtfs_realtime_pb2

from gtfs_translation.core.processor import FeedProcessor
from gtfs_translation.core.translator import MockTranslator


@pytest.mark.asyncio
async def test_old_feed_has_esla_new_needs_es419() -> None:
    """Test migration: old feed has es-LA, should be reused as es-419."""
    # Create an old feed with es-LA translations (old format)
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

    # Add es-LA translation (old format!)
    header_es = alert.header_text.translation.add()
    header_es.text = "Alerta de Servicio"
    header_es.language = "es-LA"

    # Create a new feed with the same English text
    new_feed = gtfs_realtime_pb2.FeedMessage()
    new_feed.header.gtfs_realtime_version = "2.0"
    new_feed.header.timestamp = 2000

    entity = new_feed.entity.add()
    entity.id = "alert1"
    alert = entity.alert

    # Only English text
    header_en = alert.header_text.translation.add()
    header_en.text = "Service Alert"
    header_en.language = "en"

    # Process with es-419 as target (new format)
    translator = MockTranslator()
    metrics = await FeedProcessor.process_feed(
        new_feed,
        old_feed,
        translator,
        target_langs=["es-419"],
    )

    # With migration logic, old es-LA should be reused for es-419
    assert metrics.translations_reused == 1
    assert metrics.strings_translated == 0

    # Check that the translation was applied with new code
    alert = new_feed.entity[0].alert
    translations = {t.language: t.text for t in alert.header_text.translation}
    assert "es-419" in translations
    assert translations["es-419"] == "Alerta de Servicio"
    # Old code should not be in the output
    assert "es-LA" not in translations
