from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fcontrol_api.routers import (
    auth,
    cegep,
    cities,
    indisp,
    logs,
    ops,
    postos,
    users,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(users.router)
app.include_router(cegep.router)
app.include_router(ops.router)
app.include_router(postos.router)
app.include_router(indisp.router)
app.include_router(auth.router)
app.include_router(cities.router)
app.include_router(logs.router)
