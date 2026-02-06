import base64
import inspect
import logging
import sys
import time
from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse
from jwt import PyJWTError, decode

from fcontrol_api.schemas.response import ApiErrorResponse
from fcontrol_api.settings import Settings

settings = Settings()
logger = logging.getLogger(__name__)


async def validate_token(request: Request, call_next):
    PUBLIC_ROUTES = [
        '/auth/authorize',
        '/auth/token',
        '/health',
        '/docs',
        '/openapi.json',
        '/redoc',
    ]

    # 1. Verificar se rota é pública
    if request.url.path in PUBLIC_ROUTES:
        return await call_next(request)

    # 2. Extrair token
    auth_header = request.headers.get('authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    else:
        logger.warning(
            f'Token ausente | '
            f'Path: {request.url.path} | '
            f'IP: {request.client.host} | '
            f'User-Agent: {request.headers.get("user-agent", "unknown")}'
        )
        return JSONResponse(
            status_code=401,
            content=ApiErrorResponse(
                message='Token nao fornecido',
                path=str(request.url.path),
            ).model_dump(),
        )

    # 3. DECODIFICAR TOKEN
    try:
        payload = decode(
            token,
            base64.urlsafe_b64decode(settings.SECRET_KEY + '========'),
            algorithms=[settings.ALGORITHM],
        )
        user_id = payload.get('user_id')
        app_client = payload.get('app_client')

        if not user_id:
            raise PyJWTError('user_id ausente no token')

        if not app_client:
            raise PyJWTError('app_client ausente no token')

    except PyJWTError as e:
        logger.warning(
            f'Token inválido: {e} | '
            f'Path: {request.url.path} | '
            f'IP: {request.client.host}'
        )
        return JSONResponse(
            status_code=401,
            content=ApiErrorResponse(
                message='Token invalido ou expirado',
                path=str(request.url.path),
            ).model_dump(),
        )

    # IMPLEMENTAR BLACKLIST

    # 4. Adicionar contexto de segurança ao request
    request.state.token_payload = payload
    request.state.user_id = user_id
    request.state.token = token
    request.state.app_client = app_client

    request.state.security_context = {
        'ip': request.client.host,
        'user_agent': request.headers.get('user-agent'),
        'timestamp': datetime.now(),
    }

    response = await call_next(request)
    return response


async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = (time.time() - start_time) * 1000
    response.headers['X-Process-Time'] = f'{duration:.2f}ms'

    return response


# Obtém todas as funções assíncronas definidas neste módulo
def get_middleware_stack():
    middleware_stack = []
    current_module = sys.modules[__name__]
    for _, func in inspect.getmembers(
        current_module, inspect.iscoroutinefunction
    ):
        if func.__module__ == __name__:
            middleware_stack.append(func)
    return middleware_stack


middleware_stack = get_middleware_stack()
