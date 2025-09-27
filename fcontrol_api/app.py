import time

from fastapi import FastAPI, Request
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


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)

    return response


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
