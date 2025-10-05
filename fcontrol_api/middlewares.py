import inspect
import sys
import time

from fastapi import Request, Response

from fcontrol_api.security import verify_token


# async def validate_token_and_clear_cookie(request: Request, call_next):
#     # Ignora as rotas de obtenção de credenciais
#     if request.url.path in ['/auth/authorize', '/auth/token']:
#         return await call_next(request)

#     token = request.cookies.get('token')

#     # Se não houver token
#     # Ou um token for fornecido, mas for inválido, bloqueia o acesso
#     if not token or not verify_token(token):
#         response = Response(
#             content='Token inválido ou expirado.', status_code=401
#         )
#         response.delete_cookie('token')
#         return response

#     # Se o token for válido, processa a requisição
#     response = await call_next(request)
#     return response


async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = round(time.time() - start_time, 4)
    response.headers['X-Process-Time'] = str(process_time)

    return response


def get_middleware_stack():
    middleware_stack = []
    current_module = sys.modules[__name__]
    # Obtém todas as funções assíncronas definidas neste módulo
    for _, func in inspect.getmembers(
        current_module, inspect.iscoroutinefunction
    ):
        if func.__module__ == __name__:
            middleware_stack.append(func)
    return middleware_stack


middleware_stack = get_middleware_stack()
