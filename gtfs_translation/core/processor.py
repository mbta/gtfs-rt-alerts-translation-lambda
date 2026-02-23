import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from google.protobuf import json_format
from google.transit import gtfs_realtime_pb2

from gtfs_translation.config import from_smartling_code

if TYPE_CHECKING:
    from gtfs_translation.core.translator import Translator

FeedFormat = Literal["json", "pb"]

logger = logging.getLogger(__name__)


@dataclass
class ProcessingMetrics:
    alerts_processed: int = 0
    strings_translated: int = 0
    translations_reused: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "alerts_processed": self.alerts_processed,
            "strings_translated": self.strings_translated,
            "translations_reused": self.translations_reused,
        }


class FeedProcessor:
    @staticmethod
    def parse(content: bytes, fmt: FeedFormat) -> gtfs_realtime_pb2.FeedMessage:
        feed = gtfs_realtime_pb2.FeedMessage()

        if fmt == "pb":
            feed.ParseFromString(content)
        elif fmt == "json":
            json_str = content.decode("utf-8")
            # We use ignore_unknown_fields=True to allow parsing MBTA "Enhanced" JSON
            # which contains non-standard fields.
            json_format.Parse(json_str, feed, ignore_unknown_fields=True)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        return feed

    @staticmethod
    def serialize(
        feed: gtfs_realtime_pb2.FeedMessage,
        fmt: FeedFormat,
        original_json: dict[str, Any] | None = None,
    ) -> bytes:
        if fmt == "pb":
            res: bytes = feed.SerializeToString()
            return res
        elif fmt == "json":
            # 1. Start with the Protobuf-to-JSON conversion
            json_str = json_format.MessageToJson(feed, preserving_proto_field_name=True)
            current_json = json.loads(json_str)

            # 2. If we have the original JSON, merge in the missing enhanced fields
            if original_json:
                FeedProcessor._merge_enhanced_fields(current_json, original_json)

            res_json: bytes = json.dumps(current_json, indent=2, ensure_ascii=False).encode("utf-8")
            return res_json
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    @staticmethod
    def _merge_enhanced_fields(current: dict[str, Any], original: dict[str, Any]) -> None:
        """
        Recursively merges fields from original JSON that are missing in current JSON.
        This preserves 'enhanced' fields (like effect_detail) that Protobuf doesn't know about.
        """
        # Map original entities by ID for easy lookup
        orig_entities = {e.get("id"): e for e in original.get("entity", []) if "id" in e}

        for entity in current.get("entity", []):
            eid = entity.get("id")
            orig_entity = orig_entities.get(eid)
            if not orig_entity:
                continue

            # Merge entity-level fields
            for k, v in orig_entity.items():
                if k not in entity:
                    entity[k] = v

            # Merge alert-level fields
            if "alert" in entity and "alert" in orig_entity:
                alert = entity["alert"]
                orig_alert = orig_entity["alert"]
                for k, v in orig_alert.items():
                    if k not in alert:
                        alert[k] = v

    @classmethod
    async def process_feed(
        cls,
        feed: gtfs_realtime_pb2.FeedMessage,
        old_feed: gtfs_realtime_pb2.FeedMessage | None,
        translator: "Translator",
        target_langs: list[str],
        concurrency_limit: int = 20,
        source_json: dict[str, Any] | None = None,
        dest_json: dict[str, Any] | None = None,
    ) -> ProcessingMetrics:
        """
        Translates the feed in-place.
        """
        metrics = ProcessingMetrics()

        # 1. Collect existing translations from old feeds (PB + JSON)
        old_translation_map = cls._gather_translations_from_feed(
            old_feed, dest_json, include_all_translations=True
        )

        # 2. Collect English strings from new feeds (PB + JSON)
        new_english_map = cls._gather_translations_from_feed(
            feed, source_json, include_all_translations=False
        )

        # Count alerts processed
        for entity in feed.entity:
            if entity.HasField("alert"):
                metrics.alerts_processed += 1

        # 3. Merge old translations onto new English map
        translation_map: dict[str, dict[str, str | None]] = defaultdict(dict)
        translation_map.update(
            {english: {**old_translation_map.get(english, {})} for english in new_english_map}
        )

        metrics.translations_reused = sum(
            1
            for english, translations in translation_map.items()
            if english.strip() != ""
            for lang in target_langs
            if lang in translations
        )

        # 4. Identify missing translations and batch them
        semaphore = asyncio.Semaphore(concurrency_limit)

        missing_english = [
            english
            for english, translations in translation_map.items()
            if english.strip() != "" and any(lang not in translations for lang in target_langs)
        ]

        if translator.always_translate_all:
            if missing_english:
                all_needed_english = [
                    english for english in translation_map if english.strip() != ""
                ]
            else:
                all_needed_english = []
        else:
            all_needed_english = missing_english

        if all_needed_english:
            logger.info(
                "Translating %d new strings to %s: %s",
                len(missing_english),
                ", ".join(target_langs),
                missing_english,
            )

            async with semaphore:
                translations_by_lang = await translator.translate_batch(
                    all_needed_english, target_langs
                )
                for lang, translations in translations_by_lang.items():
                    metrics.strings_translated += sum(
                        1 for translation in translations if translation is not None
                    )
                    for english, translated in zip(all_needed_english, translations, strict=True):
                        if translated is not None:
                            translation_map[english][lang] = translated

        # 3. Apply translations back to the feed
        # For empty/whitespace English strings, insert empty translations
        for english in translation_map:
            if english.strip() == "":
                for lang in target_langs:
                    translation_map[english][lang] = ""

        # Apply to Protobuf
        for entity in feed.entity:
            if not entity.HasField("alert"):
                continue
            alert = entity.alert
            for field_name in [
                "header_text",
                "description_text",
                "tts_header_text",
                "tts_description_text",
            ]:
                if not alert.HasField(field_name):
                    continue
                ts = getattr(alert, field_name)
                cls._apply_translations(ts, translation_map, target_langs)

        # Apply to Enhanced JSON
        if source_json:
            for entity_orig in source_json.get("entity", []):
                alert_orig = entity_orig.get("alert")
                if not alert_orig:
                    continue

                for field_name in ["service_effect_text", "timeframe_text"]:
                    if field_name in alert_orig:
                        cls._apply_translations_json(
                            alert_orig[field_name], translation_map, target_langs
                        )

        # Process URLs
        for entity in feed.entity:
            if entity.HasField("alert") and entity.alert.HasField("url"):
                cls._process_url(entity.alert.url, target_langs)

        return metrics

    @classmethod
    def _gather_translations_from_feed(
        cls,
        feed: gtfs_realtime_pb2.FeedMessage | None,
        json_data: dict[str, Any] | None,
        include_all_translations: bool,
    ) -> dict[str, dict[str, str]]:
        """
        Gather translations from a feed (PB + JSON).

        If include_all_translations=True, collects all non-English translations.
        If include_all_translations=False, only collects English text (maps to empty dicts).

        Returns: dict mapping english_text -> {lang -> translation}
        """
        result: dict[str, dict[str, str]] = defaultdict(dict)

        # Process Protobuf fields
        if feed:
            for entity in feed.entity:
                if not entity.HasField("alert"):
                    continue
                alert = entity.alert

                for field_name in [
                    "header_text",
                    "description_text",
                    "tts_header_text",
                    "tts_description_text",
                ]:
                    if not alert.HasField(field_name):
                        continue
                    ts = getattr(alert, field_name)
                    translations = cls._extract_translations_from_ts(ts, include_all_translations)
                    for english, trans_dict in translations.items():
                        result[english].update(trans_dict)

        # Process Enhanced JSON fields
        if json_data:
            for entity_orig in json_data.get("entity", []):
                alert_orig = entity_orig.get("alert")
                if not alert_orig:
                    continue

                # Process standard PB fields from JSON (for old feeds)
                if include_all_translations:
                    for field_name in [
                        "header_text",
                        "description_text",
                        "tts_header_text",
                        "tts_description_text",
                    ]:
                        if field_name in alert_orig:
                            translations = cls._extract_translations_from_json(
                                alert_orig[field_name], include_all_translations
                            )
                            for english, trans_dict in translations.items():
                                result[english].update(trans_dict)

                # Process enhanced fields
                for field_name in ["service_effect_text", "timeframe_text"]:
                    if field_name in alert_orig:
                        translations = cls._extract_translations_from_json(
                            alert_orig[field_name], include_all_translations
                        )
                        for english, trans_dict in translations.items():
                            result[english].update(trans_dict)

        return result

    @classmethod
    def _extract_translations_from_ts(
        cls, ts: gtfs_realtime_pb2.TranslatedString, include_all_translations: bool
    ) -> dict[str, dict[str, str]]:
        """Extract translations from a TranslatedString.

        Returns dict mapping english_text -> {lang -> translation}
        For include_all_translations=False, returns {english_text: {}}

        Normalizes language codes from old Smartling codes (es-LA) to GTFS codes (es-419).
        """
        english_text = cls._get_english_text(ts)
        if english_text is None:
            return {}

        if not include_all_translations:
            return {english_text: {}}

        translations: dict[str, str] = {}
        for t in ts.translation:
            if t.language and t.language != "en":
                # Normalize old Smartling codes to GTFS codes (e.g., es-LA -> es-419)
                normalized_lang = from_smartling_code(t.language)
                translations[normalized_lang] = t.text

        return {english_text: translations}

    @classmethod
    def _extract_translations_from_json(
        cls, ts_json: dict[str, Any], include_all_translations: bool
    ) -> dict[str, dict[str, str]]:
        """Extract translations from a JSON TranslatedString.

        Returns dict mapping english_text -> {lang -> translation}
        For include_all_translations=False, returns {english_text: {}}

        Normalizes language codes from old Smartling codes (es-LA) to GTFS codes (es-419).
        """
        english_text = None
        translations_list = ts_json.get("translation", [])
        for t in translations_list:
            if t.get("language") == "en" or not t.get("language"):
                english_text = t.get("text", "")
                break

        if english_text is None:
            return {}

        if not include_all_translations:
            return {english_text: {}}

        translations: dict[str, str] = {}
        for t in translations_list:
            lang = t.get("language")
            if lang and lang != "en":
                # Normalize old Smartling codes to GTFS codes (e.g., es-LA -> es-419)
                normalized_lang = from_smartling_code(lang)
                translations[normalized_lang] = t.get("text", "")

        return {english_text: translations}

    @classmethod
    def _apply_translations(
        cls,
        ts: gtfs_realtime_pb2.TranslatedString,
        translation_map: dict[str, dict[str, str | None]],
        target_langs: list[str],
    ) -> None:
        english_text = cls._get_english_text(ts)
        if english_text is None:
            return

        existing_langs = {t.language for t in ts.translation}
        for lang in target_langs:
            if lang not in existing_langs:
                translated_text = translation_map[english_text].get(lang)
                if translated_text is not None and (
                    translated_text != english_text or english_text.strip() == ""
                ):
                    new_t = ts.translation.add()
                    new_t.text = translated_text
                    new_t.language = lang

    @classmethod
    def _apply_translations_json(
        cls,
        ts_json: dict[str, Any],
        translation_map: dict[str, dict[str, str | None]],
        target_langs: list[str],
    ) -> None:
        english_text = None
        translations = ts_json.get("translation", [])
        existing_langs = set()
        for t in translations:
            lang = t.get("language")
            if lang == "en" or not lang:
                english_text = t.get("text", "")
            if lang:
                existing_langs.add(lang)

        if english_text is None:
            return

        for lang in target_langs:
            if lang not in existing_langs:
                translated_text = translation_map[english_text].get(lang)
                if translated_text is not None and (
                    translated_text != english_text or english_text.strip() == ""
                ):
                    translations.append({"text": translated_text, "language": lang})

    @staticmethod
    def _get_english_text(ts: gtfs_realtime_pb2.TranslatedString) -> str | None:
        if not ts:
            return None
        for t in ts.translation:
            if not t.language or t.language == "en":
                res: str = t.text
                return res
        return None

    @staticmethod
    def _process_url(ts: gtfs_realtime_pb2.TranslatedString, target_langs: list[str]) -> None:
        # URL logic: append ?locale={lang}
        # Find English URL
        english_url = ""
        for t in ts.translation:
            if not t.language or t.language == "en":
                english_url = t.text
                break

        if not english_url:
            return

        existing_langs = {t.language for t in ts.translation}

        for lang in target_langs:
            if lang in existing_langs:
                continue

            if "locale=" in english_url:
                # If the URL already contains a locale parameter, do not modify it.
                # Just copy the English URL for this lang.
                new_t = ts.translation.add()
                new_t.text = english_url
                new_t.language = lang
            else:
                separator = "&" if "?" in english_url else "?"
                new_url = f"{english_url}{separator}locale={lang}"
                new_t = ts.translation.add()
                new_t.text = new_url
                new_t.language = lang
