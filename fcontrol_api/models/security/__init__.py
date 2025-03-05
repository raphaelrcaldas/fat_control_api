import importlib
import pkgutil

from .. import public

for _, module_name, _ in pkgutil.walk_packages(
    public.__path__, public.__name__ + '.'
):
    importlib.import_module(module_name)