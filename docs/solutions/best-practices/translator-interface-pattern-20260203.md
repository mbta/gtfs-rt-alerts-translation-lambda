---
module: Architecture
date: 2026-02-03
problem_type: best_practice
component: service_object
symptoms:
  - "Need to swap translation providers without changing processor"
  - "Testing requires mock translator"
  - "Multiple Smartling API strategies exist"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags: [interface, protocol, translator, smartling, dependency-injection, testing]
---

# Best Practice: Translator Interface Pattern

## Problem
The translation service needed to be swappable to:
1. Support different translation providers in the future
2. Allow mock translators for testing
3. Support multiple Smartling API strategies (MT Router, File API, Job Batches)

## Environment
- Module: Architecture
- Affected Component: `gtfs_translation/core/translator.py`
- Date: 2026-02-03

## Solution: Abstract Base Class with Implementations

Define a `Translator` protocol (abstract base class) and implement concrete translators.

**Interface definition:**

```python
# gtfs_translation/core/translator.py

from abc import ABC, abstractmethod

class Translator(ABC):
    """Abstract base class for translation services."""
    
    # Set to True for translators that always retranslate all strings
    always_translate_all: bool = False
    
    @abstractmethod
    def translate_batch(
        self,
        texts: list[str],
        target_langs: list[str],
    ) -> dict[str, list[str]]:
        """
        Translate a batch of texts to multiple target languages.
        
        Args:
            texts: List of English strings to translate
            target_langs: List of target language codes (GTFS format)
        
        Returns:
            Dict mapping language code to list of translated strings
            (same order as input texts)
        """
        pass
    
    async def close(self) -> None:
        """Clean up resources (optional)."""
        pass
```

**Mock implementation for testing:**

```python
class MockTranslator(Translator):
    """Mock translator for testing."""
    
    def translate_batch(
        self,
        texts: list[str],
        target_langs: list[str],
    ) -> dict[str, list[str]]:
        return {
            lang: [f"[{lang}] {text}" for text in texts]
            for lang in target_langs
        }
```

**Smartling implementation:**

```python
# gtfs_translation/core/smartling.py

class SmartlingTranslator(Translator):
    """Translator using Smartling MT Router API."""
    
    def translate_batch(
        self,
        texts: list[str],
        target_langs: list[str],
    ) -> dict[str, list[str]]:
        # Synchronous interface, async internally
        return asyncio.run(self._translate_batch_async(texts, target_langs))
```

**Usage in processor:**

```python
# gtfs_translation/core/processor.py

class FeedProcessor:
    @staticmethod
    def process_feed(
        translator: Translator,  # Accept interface, not concrete type
        source_feed: bytes,
        target_langs: list[str],
        ...
    ) -> ProcessingMetrics:
        # Processor works with any Translator implementation
        translations = translator.translate_batch(texts, target_langs)
```

## Why This Works

1. **Dependency injection**: Processor receives translator, doesn't create it
2. **Testability**: Tests inject MockTranslator
3. **Flexibility**: Can swap Smartling strategies without changing processor
4. **Single responsibility**: Each translator handles its own API details

## Available Implementations

| Class | API | Use Case |
|-------|-----|----------|
| `SmartlingTranslator` | MT Router | Simple, fast translations |
| `SmartlingFileTranslator` | File MT | Bulk translations |
| `SmartlingJobBatchesTranslator` | Job Batches V2 | Human review workflow |
| `MockTranslator` | None | Testing |

## Prevention

- Always program to the interface (`Translator`), not implementations
- Add new translators by implementing the interface
- Document the `always_translate_all` flag behavior

## Related Issues

No related issues documented yet.
