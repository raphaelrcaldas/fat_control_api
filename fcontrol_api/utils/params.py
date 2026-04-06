"""Utilitários para parsing de query parameters."""

import json
from http import HTTPStatus

from fastapi import HTTPException


def parse_str_list(raw: str | None, param_name: str) -> list[str] | None:
    """Parseia um query param JSON array string para list[str].

    Levanta HTTP 422 se o JSON for inválido ou não for uma lista de strings.
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=f"Parâmetro '{param_name}' não é JSON válido.",
        )
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) for item in parsed
    ):
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=(
                f"Parâmetro '{param_name}' deve ser uma lista de strings JSON."
            ),
        )
    return parsed
