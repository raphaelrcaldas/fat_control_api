from sqlalchemy import MetaData

from .cegep.base import Base as BaseCegep
from .estatistica.base import Base as BaseStats
from .nav.base import Base as BaseNav
from .public.base import Base as BasePublic
from .security.base import Base as BaseSecurity

metadata = MetaData()
for m in [
    BasePublic.metadata,
    BaseSecurity.metadata,
    BaseCegep.metadata,
    BaseNav.metadata,
    BaseStats.metadata,
]:
    for t in m.tables.values():
        t.tometadata(metadata)
