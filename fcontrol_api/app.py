# ruff: noqa: E402
# E402 desativado: imports são intercalados com chamadas a
# mark() para instrumentação de cold start (BOOT_PROFILE=1).
from fcontrol_api.utils.boot_profiler import mark

mark('app.py: import start')

from fastapi import FastAPI
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

mark('app.py: fastapi imported')

from fcontrol_api import routers

mark('app.py: routers package imported')

from fcontrol_api.exceptions import (
    http_exception_handler,
    validation_exception_handler,
)
from fcontrol_api.middlewares import middleware_stack

mark('app.py: middlewares imported')

from fcontrol_api.settings import Settings

mark('app.py: settings imported')


# Sem lifespan: removido deliberadamente para desacoplar o boot de
# dependências externas (storage/Supabase). Inicializações preguiçosas
# (ensure_bucket, _get_client, etc.) rodam na 1ª requisição que delas
# precisar — se o storage estiver fora no momento do deploy, a API ainda
# sobe e serve endpoints que não dependem dele. Ver services/storage.py.
app = FastAPI()

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


for middleware in middleware_stack:
    app.middleware('http')(middleware)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        Settings().FATLOGIN_URL,
        Settings().FATCONTROL_URL,
        Settings().FATBIRD_URL,
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(routers.router)

mark('app.py: app fully configured')
