from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fcontrol_api.routers import auth, indisp, ops, postos, users

origins = [
    'http://localhost:3000',
    'http://localhost:3001',
    'https://fatcontrol.vercel.app'
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
app.include_router(ops.router)
app.include_router(postos.router)
app.include_router(indisp.router)
app.include_router(auth.router)
