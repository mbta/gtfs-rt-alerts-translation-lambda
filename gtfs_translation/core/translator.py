from abc import ABC, abstractmethod


class Translator(ABC):
    always_translate_all: bool = False

    @abstractmethod
    async def translate_batch(
        self, texts: list[str], target_langs: list[str]
    ) -> dict[str, list[str | None]]:
        """
        Translate multiple strings into multiple target languages.
        Returns a mapping from language code to a list of translations
        in the same order as input texts.
        """
        pass


class MockTranslator(Translator):
    async def translate_batch(
        self, texts: list[str], target_langs: list[str]
    ) -> dict[str, list[str | None]]:
        """
        Appends the language code to the text for testing.
        """
        return {lang: [f"[{lang}] {text}" for text in texts] for lang in target_langs}
