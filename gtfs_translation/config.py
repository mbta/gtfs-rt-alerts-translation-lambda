import os


class Settings:
    def __init__(self) -> None:
        self.smartling_user_id = os.environ.get("SMARTLING_USER_ID", "")
        self.smartling_user_secret = os.environ.get("SMARTLING_USER_SECRET", "")
        self.smartling_user_secret_arn = os.environ.get("SMARTLING_USER_SECRET_ARN", "")
        self.smartling_account_uid = os.environ.get("SMARTLING_ACCOUNT_UID", "")
        self.source_url = os.environ.get("SOURCE_URL", "")
        self.destination_bucket_url = os.environ.get("DESTINATION_BUCKET_URL", "")
        self.target_languages = os.environ.get("TARGET_LANGUAGES", "es")
        self.concurrency_limit = int(os.environ.get("CONCURRENCY_LIMIT", "20"))

    @property
    def target_lang_list(self) -> list[str]:
        return [lang.strip() for lang in self.target_languages.split(",") if lang.strip()]


settings = Settings()
