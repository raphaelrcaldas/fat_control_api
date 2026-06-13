"""Integracao com o Portal da Transparencia (CGU).

Endpoint principal:
    GET https://api.portaldatransparencia.gov.br/api-de-dados/servidores/remuneracao

Autenticacao via header `chave-api-dados`. Limite oficial: 90 req/min
(700 req/min entre 00h e 06h).
"""

import logging
from datetime import date
from decimal import Decimal
from functools import lru_cache
from http import HTTPStatus
from typing import Optional, TypedDict

import httpx
from fastapi import HTTPException
from httpx import AsyncClient

from fcontrol_api.settings import Settings

logger = logging.getLogger(__name__)

PORTAL_BASE_URL = 'https://api.portaldatransparencia.gov.br'


class RemuneracaoPortal(TypedDict):
    """Resposta normalizada do Portal para um servidor em um mes."""

    mes_ano: date
    remuneracao_bruta: Optional[Decimal]
    remuneracao_liquida: Optional[Decimal]


@lru_cache
def _get_settings() -> Settings:
    return Settings()


def portal_client() -> AsyncClient:
    settings = _get_settings()
    return AsyncClient(
        base_url=PORTAL_BASE_URL,
        headers={'chave-api-dados': settings.PORTAL_API_KEY},
        timeout=15,
    )


def _to_decimal(value) -> Optional[Decimal]:
    """Converte valores monetarios do Portal em Decimal.

    Aceita formatos: numero, '1.234,56', '- 1.514,51', '0,00'.
    Strings vazias viram None; zero numerico vira Decimal('0').
    """
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    s = str(value).strip()
    if not s:
        return None
    # Formato BR: "1.234,56" ou "- 1.514,51"
    s = s.replace(' ', '').replace('.', '').replace(',', '.')
    try:
        return Decimal(s)
    except Exception:
        return None


def _extract_remuneracao(
    dto: dict,
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Extrai bruta e liquida de um item de `remuneracoesDTO`.

    Campos conforme JSON real do endpoint /servidores/remuneracao:
    - `remuneracaoBasicaBruta`: bruta (string BR)
    - `valorTotalRemuneracaoAposDeducoes`: liquida (string BR)
    """
    bruta = _to_decimal(dto.get('remuneracaoBasicaBruta'))
    liquida = _to_decimal(dto.get('valorTotalRemuneracaoAposDeducoes'))
    return bruta, liquida


def _parse_sk_mes_referencia(sk: object) -> Optional[date]:
    """Converte `skMesReferencia` em date.

    Aceita ISO 'YYYY-MM-DD' (formato real observado) e AAAAMM.
    """
    if not sk:
        return None
    s = str(sk).strip()
    # Formato ISO: '2026-03-01'
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    # Formato AAAAMM (fallback)
    if len(s) == 6 and s.isdigit():
        ano = int(s[:4])
        mes = int(s[4:])
        if 1 <= mes <= 12:
            return date(ano, mes, 1)
    return None


async def buscar_remuneracao(cpf: str, mes_ano: date) -> RemuneracaoPortal:
    """Busca a remuneracao de um servidor por CPF em um mes especifico.

    :param cpf: CPF com 11 digitos numericos.
    :param mes_ano: Data; sera convertida para AAAAMM.
    :raises HTTPException: 4xx/5xx do Portal sao mapeados para a API.
    """
    settings = _get_settings()
    if not settings.PORTAL_API_KEY:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail='Chave do Portal da Transparencia nao configurada',
        )

    if not cpf or len(cpf) != 11:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='CPF invalido para consulta ao Portal',
        )

    mes_ano_int = mes_ano.year * 100 + mes_ano.month
    cpf_mask = f'***.***.{cpf[6:9]}-**'
    logger.info('Portal query cpf=%s mesAno=%d', cpf_mask, mes_ano_int)

    async with portal_client() as client:
        try:
            response = await client.get(
                '/api-de-dados/servidores/remuneracao',
                params={
                    'cpf': cpf,
                    'mesAno': mes_ano_int,
                    'pagina': 1,
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            upstream = e.response.status_code
            logger.warning(
                'Portal retornou %d para cpf=%s mesAno=%d',
                upstream,
                cpf_mask,
                mes_ano_int,
            )
            if upstream == HTTPStatus.NOT_FOUND:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=('CPF não encontrado no Portal da Transparência'),
                ) from e
            if upstream in {
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
            }:
                raise HTTPException(
                    status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                    detail=(
                        'Chave de acesso ao Portal da Transparência '
                        'inválida ou expirada'
                    ),
                ) from e
            if upstream == HTTPStatus.TOO_MANY_REQUESTS:
                raise HTTPException(
                    status_code=HTTPStatus.TOO_MANY_REQUESTS,
                    detail=(
                        'Limite de requisições ao Portal atingido '
                        '(90/min). Tente novamente em instantes.'
                    ),
                ) from e
            raise HTTPException(
                status_code=HTTPStatus.BAD_GATEWAY,
                detail=f'Portal da Transparência respondeu {upstream}',
            ) from e
        except httpx.RequestError as e:
            logger.warning(
                'Falha de rede ao consultar Portal cpf=%s: %s',
                cpf_mask,
                e,
            )
            raise HTTPException(
                status_code=HTTPStatus.GATEWAY_TIMEOUT,
                detail='Falha de rede ao consultar Portal da Transparência',
            ) from e

        data = response.json()

    if not data:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=(
                'Nenhuma remuneracao encontrada para este CPF/mes no Portal'
            ),
        )

    # Estrutura real: [{ "servidor": {...}, "remuneracoesDTO": [{...}] }]
    servidor_item = data[0] if isinstance(data, list) else data
    remuneracoes = servidor_item.get('remuneracoesDTO') or []
    if not remuneracoes:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=(
                'Servidor encontrado, mas sem remuneracao para o mes no Portal'
            ),
        )

    dto = remuneracoes[0]
    bruta, liquida = _extract_remuneracao(dto)

    # `skMesReferencia` (ISO) e a chave oficial do mes na resposta.
    # Fallback para o mes_ano do request se ausente.
    mes_ref = _parse_sk_mes_referencia(dto.get('skMesReferencia')) or date(
        mes_ano.year, mes_ano.month, 1
    )

    return RemuneracaoPortal(
        mes_ano=mes_ref,
        remuneracao_bruta=bruta,
        remuneracao_liquida=liquida,
    )
