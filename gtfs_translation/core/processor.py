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
        enhanced: bool = False,
    ) -> bytes:
        if fmt == "pb":
            res: bytes = feed.SerializeToString()
            return res
        elif fmt == "json":
            # 1. Start with the Protobuf-to-JSON conversion
            json_str = json_format.MessageToJson(feed, preserving_proto_field_name=True)
            current_json = json.loads(json_str)

            # 2. If we have the original JSON, restore types and merge fields
            if original_json:
                FeedProcessor._restore_types(current_json, original_json)
                # Always merge experimental GTFS-RT fields (cause_detail, effect_detail)
                # These are part of the spec but not in our protobuf bindings
                FeedProcessor._merge_experimental_fields(current_json, original_json)
                # Only merge MBTA-specific enhanced fields for enhanced output
                if enhanced:
                    FeedProcessor._merge_enhanced_fields(current_json, original_json)

            res_json: bytes = json.dumps(current_json, indent=2, ensure_ascii=False).encode("utf-8")
            return res_json
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    @staticmethod
    def _restore_types(current: Any, original: Any) -> None:
        """
        Recursively restore types from original JSON.

        Protobuf's MessageToJson converts uint64/int64 fields to strings.
        This restores the original numeric types when we have the source JSON.
        """
        if isinstance(current, dict) and isinstance(original, dict):
            for key in current:
                if key in original:
                    orig_val = original[key]
                    curr_val = current[key]

                    # If original was numeric and current is string, restore the type
                    if isinstance(orig_val, (int, float)) and isinstance(curr_val, str):
                        try:
                            if isinstance(orig_val, int):
                                current[key] = int(curr_val)
                            else:
                                current[key] = float(curr_val)
                        except ValueError:
                            pass  # Keep the string if conversion fails
                    elif isinstance(curr_val, (dict, list)):
                        FeedProcessor._restore_types(curr_val, orig_val)

        elif isinstance(current, list) and isinstance(original, list):
            # For lists, we need to match by position or by ID
            if len(current) > 0 and isinstance(current[0], dict):
                # Try to match by "id" field (for entities)
                orig_by_id = {}
                for item in original:
                    if isinstance(item, dict) and "id" in item:
                        orig_by_id[item["id"]] = item

                for curr_item in current:
                    if isinstance(curr_item, dict):
                        if "id" in curr_item and curr_item["id"] in orig_by_id:
                            FeedProcessor._restore_types(curr_item, orig_by_id[curr_item["id"]])
                        elif len(original) == len(current):
                            # Fallback to positional matching if same length
                            idx = current.index(curr_item)
                            if idx < len(original):
                                FeedProcessor._restore_types(curr_item, original[idx])
            else:
                # For simple lists or same-length lists, match by position
                for i, curr_item in enumerate(current):
                    if i < len(original):
                        if isinstance(curr_item, (dict, list)):
                            FeedProcessor._restore_types(curr_item, original[i])
                        elif isinstance(original[i], (int, float)) and isinstance(curr_item, str):
                            try:
                                if isinstance(original[i], int):
                                    current[i] = int(curr_item)
                                else:
                                    current[i] = float(curr_item)
                            except ValueError:
                                pass

    # Experimental GTFS-RT fields that are in the spec but not in our protobuf bindings.
    # These should be preserved as raw strings in JSON output (not TranslatedStrings).
    # See: https://github.com/google/transit/blob/master/gtfs-realtime/proto/gtfs-realtime.proto
    EXPERIMENTAL_ALERT_FIELDS = ("cause_detail", "effect_detail")

    @staticmethod
    def _merge_experimental_fields(current: dict[str, Any], original: dict[str, Any]) -> None:
        """
        Merge experimental GTFS-RT fields from original JSON.

        These fields (cause_detail, effect_detail) are defined in the GTFS-RT spec as
        TranslatedString but our protobuf bindings don't include them. The MBTA feed
        uses them as raw strings. We preserve them as-is without translation.
        """
        orig_entities = {e.get("id"): e for e in original.get("entity", []) if "id" in e}

        for entity in current.get("entity", []):
            eid = entity.get("id")
            orig_entity = orig_entities.get(eid)
            if not orig_entity:
                continue

            if "alert" in entity and "alert" in orig_entity:
                alert = entity["alert"]
                orig_alert = orig_entity["alert"]
                for field in FeedProcessor.EXPERIMENTAL_ALERT_FIELDS:
                    if field in orig_alert and field not in alert:
                        alert[field] = orig_alert[field]

    @staticmethod
    def _merge_enhanced_fields(current: dict[str, Any], original: dict[str, Any]) -> None:
        """
        Recursively merges fields from original JSON that are missing in current JSON.
        This preserves 'enhanced' fields (like activities) that Protobuf
        doesn't know about.
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

                # Merge informed_entity fields (e.g., activities, facility_id)
                FeedProcessor._merge_informed_entity_fields(alert, orig_alert)

    @staticmethod
    def _merge_informed_entity_fields(alert: dict[str, Any], orig_alert: dict[str, Any]) -> None:
        """
        Merge enhanced fields within informed_entity items.

        The informed_entity array can have enhanced fields like 'activities' and 'facility_id'
        that are not part of the standard GTFS-RT spec and get stripped during protobuf parsing.
        """
        curr_entities = alert.get("informed_entity", [])
        orig_entities = orig_alert.get("informed_entity", [])

        if not curr_entities or not orig_entities:
            return

        # Match by position since informed_entity items don't have a unique ID
        for i, curr_ie in enumerate(curr_entities):
            if i < len(orig_entities):
                orig_ie = orig_entities[i]
                # Merge any fields from original that are missing in current
                for k, v in orig_ie.items():
                    if k not in curr_ie:
                        curr_ie[k] = v

    @classmethod
    def apply_cached_translations(
        cls,
        feed: gtfs_realtime_pb2.FeedMessage,
        old_feed: gtfs_realtime_pb2.FeedMessage | None,
        target_langs: list[str],
        source_json: dict[str, Any] | None = None,
        dest_json: dict[str, Any] | None = None,
    ) -> int:
        """
        Apply only cached translations from old_feed to feed, without calling translator.

        Use this as a fallback when translation times out or fails.

        Returns: number of translations applied
        """
        # 1. Collect existing translations from old feeds (PB + JSON)
        old_translation_map = cls._gather_translations_from_feed(
            old_feed, dest_json, include_all_translations=True
        )

        if not old_translation_map:
            return 0

        # 2. Collect English strings from new feeds (PB + JSON)
        new_english_map = cls._gather_translations_from_feed(
            feed, source_json, include_all_translations=False
        )

        # 3. Build translation map with only old translations
        translation_map: dict[str, dict[str, str | None]] = defaultdict(dict)
        translation_map.update(
            {english: {**old_translation_map.get(english, {})} for english in new_english_map}
        )

        # For empty/whitespace English strings, insert empty translations
        for english in translation_map:
            if english.strip() == "":
                for lang in target_langs:
                    translation_map[english][lang] = ""

        translations_applied = 0

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
                translations_applied += cls._apply_translations_count(
                    ts, translation_map, target_langs
                )

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

        return translations_applied

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
        logger.debug("Old translation map: %s", old_translation_map)

        # 2. Collect English strings from new feeds (PB + JSON)
        new_english_map = cls._gather_translations_from_feed(
            feed, source_json, include_all_translations=False
        )
        logger.debug("New English map: %s", new_english_map)

        # Count alerts processed
        for entity in feed.entity:
            if entity.HasField("alert"):
                metrics.alerts_processed += 1

        # 3. Merge old translations onto new English map
        translation_map: dict[str, dict[str, str | None]] = defaultdict(dict)
        translation_map.update(
            {english: {**old_translation_map.get(english, {})} for english in new_english_map}
        )
        logger.debug("Translation map after merge: %s", translation_map)

        # Check for partial translations and log warnings
        for english, trans_dict in translation_map.items():
            if english.strip() == "":
                continue
            missing_langs = [lang for lang in target_langs if lang not in trans_dict]
            if missing_langs and trans_dict:  # Has some translations but not all
                logger.warning(
                    "Partial translations detected for '%s': missing %s, has %s",
                    english,
                    missing_langs,
                    list(trans_dict.keys()),
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

        if missing_english:
            logger.debug("Missing translations: %s", missing_english)
            for english in missing_english:
                logger.debug(
                    "  '%s' missing langs: %s",
                    english,
                    [lang for lang in target_langs if lang not in translation_map[english]],
                )

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
        Strips leading/trailing whitespace from English text for consistent lookup.
        """
        english_text = cls._get_english_text(ts)
        if english_text is None:
            return {}

        # Strip whitespace for consistent translation lookup
        english_text = english_text.strip()

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
        Strips leading/trailing whitespace from English text for consistent lookup.
        """
        english_text = None
        translations_list = ts_json.get("translation", [])
        for t in translations_list:
            if t.get("language") == "en" or not t.get("language"):
                english_text = t.get("text", "")
                break

        if english_text is None:
            return {}

        # Strip whitespace for consistent translation lookup
        english_text = english_text.strip()

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
        cls._apply_translations_count(ts, translation_map, target_langs)

    @classmethod
    def _apply_translations_count(
        cls,
        ts: gtfs_realtime_pb2.TranslatedString,
        translation_map: dict[str, dict[str, str | None]],
        target_langs: list[str],
    ) -> int:
        """Apply translations and return count of translations applied."""
        english_text = cls._get_english_text(ts)
        if english_text is None:
            return 0

        # Strip whitespace to match the translation map keys
        english_text_stripped = english_text.strip()
        count = 0

        existing_langs = {t.language for t in ts.translation}
        for lang in target_langs:
            if lang not in existing_langs:
                translated_text = translation_map[english_text_stripped].get(lang)
                if translated_text is not None and (
                    translated_text != english_text_stripped or english_text_stripped == ""
                ):
                    new_t = ts.translation.add()
                    new_t.text = translated_text
                    new_t.language = lang
                    count += 1

        return count

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

        # Strip whitespace to match the translation map keys
        english_text_stripped = english_text.strip()

        for lang in target_langs:
            if lang not in existing_langs:
                translated_text = translation_map[english_text_stripped].get(lang)
                if translated_text is not None and (
                    translated_text != english_text_stripped or english_text_stripped.strip() == ""
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
