from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(MappedAsDataclass, DeclarativeBase):
    """Base para todas as models do schema inteligencia"""

    __table_args__ = {'schema': 'inteligencia'}
