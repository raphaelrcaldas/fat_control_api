from fastapi import Depends

from fcontrol_api.security import require_admin
from fcontrol_api.utils.router_loader import load_routers

router = load_routers(
    __path__,
    __name__,
    prefix='/security',
    dependencies=[Depends(require_admin)],
)
