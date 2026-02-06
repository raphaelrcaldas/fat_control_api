from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from fcontrol_api.schemas.response import ApiErrorResponse


async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """Handler para HTTPException retornando ApiErrorResponse."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiErrorResponse(
            message=str(exc.detail),
            path=str(request.url.path),
        ).model_dump(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handler para erros de validação do Pydantic."""
    errors = {
        '.'.join(str(loc) for loc in e['loc']): e['msg'] for e in exc.errors()
    }
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        content=ApiErrorResponse(
            message='Erro de validacao',
            errors=errors,
            path=str(request.url.path),
        ).model_dump(),
    )
