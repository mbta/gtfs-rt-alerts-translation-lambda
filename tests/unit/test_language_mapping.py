"""Tests for language code mapping between GTFS and Smartling."""

from gtfs_translation.config import from_smartling_code, to_smartling_code


def test_to_smartling_code_es419() -> None:
    """Test that es-419 is mapped to es-LA for Smartling API."""
    assert to_smartling_code("es-419") == "es-LA"


def test_to_smartling_code_passthrough() -> None:
    """Test that unmapped codes pass through unchanged."""
    assert to_smartling_code("fr") == "fr"
    assert to_smartling_code("pt") == "pt"
    assert to_smartling_code("zh") == "zh"


def test_from_smartling_code_esla() -> None:
    """Test that es-LA is mapped back to es-419 for GTFS output."""
    assert from_smartling_code("es-LA") == "es-419"


def test_from_smartling_code_passthrough() -> None:
    """Test that unmapped codes pass through unchanged."""
    assert from_smartling_code("fr") == "fr"
    assert from_smartling_code("pt") == "pt"
    assert from_smartling_code("zh") == "zh"


def test_roundtrip() -> None:
    """Test that mapping is reversible."""
    assert from_smartling_code(to_smartling_code("es-419")) == "es-419"
    assert to_smartling_code(from_smartling_code("es-LA")) == "es-LA"
