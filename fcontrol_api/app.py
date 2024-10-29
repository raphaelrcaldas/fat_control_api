from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fcontrol_api.routers import quads, tripulantes, users

origins = [
    'http://localhost:3000',
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(users.router)
app.include_router(quads.router)
app.include_router(tripulantes.router)
