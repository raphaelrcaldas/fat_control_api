from sqlalchemy import MetaData

from .aeromedica.base import Base as BaseAeromedica
from .cegep.base import Base as BaseCegep
from .estatistica.base import Base as BaseStats
from .instrucao.base import Base as BaseInstrucao
from .nav.base import Base as BaseNav
from .public.base import Base as BasePublic
from .security.base import Base as BaseSecurity
from .seg_voo.base import Base as BaseSegVoo

metadata = MetaData()
for m in [
    BasePublic.metadata,
    BaseSecurity.metadata,
    BaseCegep.metadata,
    BaseNav.metadata,
    BaseStats.metadata,
    BaseAeromedica.metadata,
    BaseSegVoo.metadata,
    BaseInstrucao.metadata,
]:
    for t in m.tables.values():
        t.tometadata(metadata)
