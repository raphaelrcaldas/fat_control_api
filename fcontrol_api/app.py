from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fcontrol_api import routers
from fcontrol_api.middlewares import middleware_stack
from fcontrol_api.settings import Settings

app = FastAPI()


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


# fcontrol_api/app.py
@app.get('/health')
async def health():
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}
