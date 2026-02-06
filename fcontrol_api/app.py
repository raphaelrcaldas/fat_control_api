from fastapi import FastAPI
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from fcontrol_api import routers
from fcontrol_api.exceptions import (
    http_exception_handler,
    validation_exception_handler,
)
from fcontrol_api.middlewares import middleware_stack
from fcontrol_api.settings import Settings

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
