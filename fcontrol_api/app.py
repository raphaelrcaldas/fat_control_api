from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fcontrol_api.routers import auth, indisp, ops, postos, users
from fcontrol_api.settings import Settings

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=Settings().CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(users.router)
app.include_router(ops.router)
app.include_router(postos.router)
app.include_router(indisp.router)
app.include_router(auth.router)
