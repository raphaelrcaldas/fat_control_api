from functools import lru_cache

from httpx import AsyncClient

from fcontrol_api.settings import Settings


@lru_cache
def _get_settings() -> Settings:
    return Settings()


def aisweb_client() -> AsyncClient:
    settings = _get_settings()
    return AsyncClient(
        base_url='https://aisweb.decea.gov.br/api/',
        params={
            'apiKey': settings.AISWEB_API_KEY,
            'apiPass': settings.AISWEB_API_PASS,
        },
        timeout=10,
        follow_redirects=True,
        headers={'User-Agent': 'Mozilla/5.0'},
    )
