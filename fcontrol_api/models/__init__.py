from .public.base import Base as BasePublic
from .security.resources import Base as BaseSecurity

metadata = [BasePublic.metadata, BaseSecurity.metadata]
