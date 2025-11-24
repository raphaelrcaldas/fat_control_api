import importlib
import pkgutil

from fastapi import APIRouter

from fcontrol_api.settings import Settings

settings = Settings()


def load_routers(path: list[str], name: str, prefix: str = '') -> APIRouter:
    """
    Carrega dinamicamente os roteadores de um pacote no mesmo nível.

    Args:
        path (list[str]): O caminho do pacote (geralmente __path__).
        name (str): O nome do pacote (geralmente __name__).
        prefix (str, optional): Um prefixo a ser adicionado a todas as rotas.
            Defaults to ''.

    Returns:
        APIRouter: Uma instância de APIRouter com os roteadores incluídos.
    """
    router = APIRouter()
    loaded_modules = []

    # Itera sobre os módulos no mesmo nível do pacote
    for loader, module_name, is_pkg in pkgutil.iter_modules(path):
        full_module_name = f'{name}.{module_name}'
        try:
            # Importa o módulo dinamicamente
            module = importlib.import_module(full_module_name)
            # Se o módulo tiver um atributo 'router', inclui ele
            if hasattr(module, 'router'):
                router.include_router(module.router, prefix=prefix)
                loaded_modules.append(module_name)
        except Exception as e:
            if settings.ENV == 'development':
                print(f'Erro ao importar o roteador {full_module_name}: {e}')

    if settings.ENV == 'development' and loaded_modules:
        print(f'Módulo "{name}" carregou os roteadores de: {loaded_modules}')

    return router
