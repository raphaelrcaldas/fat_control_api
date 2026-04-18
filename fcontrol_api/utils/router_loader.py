import importlib
import logging
import pkgutil
from typing import Sequence

from fastapi import APIRouter
from fastapi.params import Depends

from fcontrol_api.settings import Settings
from fcontrol_api.utils.boot_profiler import mark

logger = logging.getLogger(__name__)
settings = Settings()


def load_routers(
    path: list[str],
    name: str,
    prefix: str = '',
    dependencies: Sequence[Depends] | None = None,
) -> APIRouter:
    """
    Carrega dinamicamente os roteadores de um pacote no mesmo nível.

    Args:
        path (list[str]): O caminho do pacote (geralmente __path__).
        name (str): O nome do pacote (geralmente __name__).
        prefix (str, optional): Um prefixo a ser adicionado a todas as rotas.
            Defaults to ''.
        dependencies (Sequence[Depends] | None, optional): Dependências a serem
            aplicadas a todos os roteadores carregados. Defaults to None.

    Returns:
        APIRouter: Uma instância de APIRouter com os roteadores incluídos.
    """
    router = APIRouter(dependencies=dependencies)
    loaded_modules = []

    # Itera sobre os módulos no mesmo nível do pacote
    for loader, module_name, is_pkg in pkgutil.iter_modules(path):
        full_module_name = f'{name}.{module_name}'
        try:
            # Importa o módulo dinamicamente
            module = importlib.import_module(full_module_name)
            # Só sinaliza routers que custam > 100ms
            mark(
                f'router_loader: {full_module_name}',
                threshold_ms=100.0,
            )
            # Se o módulo tiver um atributo 'router', inclui ele
            if hasattr(module, 'router'):
                router.include_router(module.router, prefix=prefix)
                loaded_modules.append(module_name)
        except Exception:
            # SEMPRE loga: falha de import de router em produção é um bug
            # silencioso crítico (endpoints somem sem aviso). Em dev o
            # logger vai pro console; em prod pro sistema de logs.
            logger.exception(
                'Erro ao importar o roteador %s', full_module_name
            )

    if settings.ENV == 'development' and loaded_modules:
        print(f'Módulo "{name}" carregou os roteadores de: {loaded_modules}')

    return router
