from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_env: str = "development"
    app_secret_key: str = "change_me"
    base_url: str = "http://localhost:8000"

    # Database
    database_url: str = "postgresql+asyncpg://vericlaim:secret@localhost:5432/vericlaim"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite-preview-06-17"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_whatsapp_number: str = "whatsapp:+14155238886"

    # Meta WhatsApp Cloud API
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = "vericlaim_secret"
    whatsapp_api_version: str = "v20.0"

    # Cloudflare R2
    cloudflare_r2_endpoint: str = ""
    cloudflare_r2_access_key: str = ""
    cloudflare_r2_secret_key: str = ""
    cloudflare_r2_bucket: str = "vericlaim-media"

    # Ngrok
    ngrok_authtoken: str = ""
    ngrok_static_domain: str = ""

    # Whisper
    whisper_model: str = "base"
    whisper_device: str = "cpu"

    # Piper TTS
    piper_model_path: str = "audio/en_US-lessac-medium.onnx"
    piper_voice: str = "en_US-lessac-medium"

    # Feature flags
    use_twilio_whatsapp: bool = True
    use_local_whisper: bool = False

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def whatsapp_api_base(self) -> str:
        return f"https://graph.facebook.com/{self.whatsapp_api_version}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
