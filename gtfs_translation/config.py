from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    smartling_user_id: str
    smartling_user_secret: str = ""
    smartling_user_secret_arn: str = ""
    smartling_account_uid: str

    source_url: str = ""
    destination_bucket_url: str = ""
    target_languages: str = "es"  # Comma-separated
    concurrency_limit: int = 20

    @property
    def target_lang_list(self) -> list[str]:
        return [lang.strip() for lang in self.target_languages.split(",") if lang.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
