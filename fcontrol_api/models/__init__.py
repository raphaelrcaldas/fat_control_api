from sqlalchemy import MetaData

from .cegep.base import Base as BaseCegep
from .public.base import Base as BasePublic
from .security.base import Base as BaseSecurity

metadata = MetaData()
for m in [BasePublic.metadata, BaseSecurity.metadata, BaseCegep.metadata]:
    for t in m.tables.values():
        t.tometadata(metadata)
