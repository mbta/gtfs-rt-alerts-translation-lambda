---
title: Decouple translation gathering from alert IDs
type: fix
date: 2026-02-20
---

# Decouple translation gathering from alert IDs

## Overview
Update translation gathering to ignore alert IDs when reusing translations. Collect all existing translations from the old feed and all English texts from the new feed (PB + JSON), compare dictionaries to find missing translations, then merge newly translated results on top of existing translations before applying them to outputs.

## Problem Statement / Motivation
Current translation reuse depends on matching alert IDs and paired translated strings. If alert IDs change between feeds, existing translations are not reused. We need to reuse translations across feeds independent of IDs and ensure translations are gathered from both PB and enhanced JSON sources.

## Proposed Solution
1. Build an `old_translation_map` by scanning all old PB alerts and old JSON alerts for translations keyed by English text.
2. Build a `new_english_map` by scanning all new PB alerts and new JSON alerts for English text keys with empty translation sets.
3. Determine missing translations by comparing `new_english_map` to `old_translation_map` by target languages.
4. Run batch translation for missing texts only (unless `always_translate_all` forces full translation).
5. Merge new translations on top of old translations to produce a final `translation_map`.
6. Apply the merged `translation_map` to PB and JSON feeds.

## Technical Considerations
- Reuse existing translation application logic in `FeedProcessor._apply_translations*`.
- Add or refactor collection helpers to support:
  - collecting all translations from old feeds (PB + JSON) without ID matching.
  - collecting English text keys from new feeds (PB + JSON).
- Preserve metrics: reuse count should reflect reused translations from old feeds.
- Respect `always_translate_all` behavior for translator implementations.

## Acceptance Criteria
- [x] Existing translations are reused even when alert IDs differ between old and new feeds.
- [x] Both PB and enhanced JSON fields contribute to translation reuse and English collection.
- [x] Missing translations are determined by comparing English-text dictionaries, not by alert ID.
- [x] New translations overwrite old translations for the same English text when merged.
- [x] Unit tests cover the ID-mismatch reuse scenario and pass.

## MVP Structure

### gtfs_translation/core/processor.py
- Collect old translations across all alerts into `old_translation_map`.
- Collect new English texts across all alerts into `new_english_map`.
- Compare dictionaries to find missing translations and run batch translation.
- Merge new translations onto old translations and apply to feeds.

### tests/unit/test_processor.py
- Add a test with different alert IDs sharing the same English text to assert reuse.
- Update any expectations that assumed ID-based reuse.

## References & Research
- `gtfs_translation/core/processor.py`
- `tests/unit/test_processor.py`
