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
    ORIGINS: str

    @property
    def CORS_ORIGINS(self):
        origins = self.ORIGINS
        return [
            origin.strip() for origin in origins.split(',') if origin.strip()
        ]
