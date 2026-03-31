from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8'
    )

    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    DEFAULT_USER_PASSWORD: str
    FATLOGIN_URL: str
    FATCONTROL_URL: str
    FATBIRD_URL: str
    ENV: str = 'production'

    # AISWEB DECEA
    AISWEB_API_KEY: str = ''
    AISWEB_API_PASS: str = ''

    # Storage (MinIO local / Supabase S3 prod)
    STORAGE_ENDPOINT: str = 'localhost:9000'
    STORAGE_ACCESS_KEY: str
    STORAGE_SECRET_KEY: str
    STORAGE_BUCKET: str = 'atas-inspecao'
    STORAGE_SECURE: bool = False
    STORAGE_REGION: str = 'sa-east-1'
