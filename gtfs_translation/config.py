import os

# Language code mapping from GTFS standard codes to Smartling API codes
# Smartling uses es-LA for Latin American Spanish, while GTFS uses es-419
SMARTLING_LANGUAGE_MAP = {
    "es-419": "es-LA",
}


def to_smartling_code(lang: str) -> str:
    """Convert a GTFS language code to Smartling API language code."""
    return SMARTLING_LANGUAGE_MAP.get(lang, lang)


def from_smartling_code(lang: str) -> str:
    """Convert a Smartling API language code to GTFS language code."""
    reverse_map = {v: k for k, v in SMARTLING_LANGUAGE_MAP.items()}
    return reverse_map.get(lang, lang)


class Settings:
    def __init__(self) -> None:
        self.smartling_user_id = os.environ.get("SMARTLING_USER_ID", "")
        self.smartling_user_secret = os.environ.get("SMARTLING_USER_SECRET", "")
        self.smartling_user_secret_arn = os.environ.get("SMARTLING_USER_SECRET_ARN", "")
        self.smartling_account_uid = os.environ.get("SMARTLING_ACCOUNT_UID", "")
        self.smartling_project_id = os.environ.get("SMARTLING_PROJECT_ID", "")
        self.smartling_job_name_template = os.environ.get(
            "SMARTLING_JOB_NAME_TEMPLATE", "GTFS Alerts Translation"
        )
        self.source_url = os.environ.get("SOURCE_URL", "")
        self.destination_bucket_urls = os.environ.get("DESTINATION_BUCKET_URLS", "")
        self.target_languages = os.environ.get("TARGET_LANGUAGES", "es-419")
        self.concurrency_limit = int(os.environ.get("CONCURRENCY_LIMIT", "20"))
        self.log_level = os.environ.get("LOG_LEVEL", "NOTICE")

    @property
    def destination_bucket_url_list(self) -> list[str]:
        return [url.strip() for url in self.destination_bucket_urls.split(",") if url.strip()]

    @property
    def target_lang_list(self) -> list[str]:
        return [lang.strip() for lang in self.target_languages.split(",") if lang.strip()]


settings = Settings()
