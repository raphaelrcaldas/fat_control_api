from http import HTTPStatus

from fastapi import FastAPI

from fcontrol_api.routers import quads, tripulantes, users
from fcontrol_api.schemas import Message

app = FastAPI()

app.include_router(users.router)
app.include_router(quads.router)
app.include_router(tripulantes.router)


@app.get('/', status_code=HTTPStatus.OK, response_model=Message)
def read_root():
    return {'message': 'Olá Mundo'}
