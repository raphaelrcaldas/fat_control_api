from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    # Token de primeiro login (troca de senha obrigatória): curta duração.
    FIRST_LOGIN_TOKEN_EXPIRE_MINUTES: int = 15
    DEFAULT_USER_PASSWORD: str
    FATLOGIN_URL: str
    FATCONTROL_URL: str
    FATBIRD_URL: str
    ENV: str = 'production'
    BOOT_PROFILE: bool = False

    # AISWEB DECEA
    AISWEB_API_KEY: str = ''
    AISWEB_API_PASS: str = ''

    # Portal da Transparência (CGU)
    PORTAL_API_KEY: str = ''

    # Storage (MinIO local / Supabase S3 prod). O NOME DO BUCKET não é
    # config: cada domínio declara o seu como constante no próprio router
    # (ex.: BUCKET = 'aeromedica'). Aqui ficam só credencial e endpoint.
    STORAGE_ENDPOINT: str = 'localhost:9000'
    STORAGE_ACCESS_KEY: str
    STORAGE_SECRET_KEY: str
    STORAGE_SECURE: bool = False
    STORAGE_REGION: str = 'sa-east-1'
