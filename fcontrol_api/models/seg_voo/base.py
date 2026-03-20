from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(MappedAsDataclass, DeclarativeBase):
    """Base para todas as models do schema seg_voo"""

    __table_args__ = {'schema': 'seg_voo'}
