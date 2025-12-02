import importlib
import pkgutil

from .. import nav

for _, module_name, _ in pkgutil.walk_packages(
    nav.__path__, nav.__name__ + '.'
):
    importlib.import_module(module_name)
