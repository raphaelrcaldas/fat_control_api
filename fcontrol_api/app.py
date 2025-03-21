import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fcontrol_api.routers import auth, indisp, ops, postos, users

origins = [
    'http://localhost:3000',
]


@asynccontextmanager
async def run_migrations(app: FastAPI):
    """Executa as migrações do Alembic antes da inicialização da aplicação."""
    try:
        subprocess.run(['alembic', 'upgrade', 'head'], check=True)
        print('Migrações do Alembic aplicadas com sucesso!')
    except subprocess.CalledProcessError as e:
        print(f'Erro ao aplicar migrações: {e}')
    yield


app = FastAPI(lifespan=run_migrations)

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
