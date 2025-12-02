from sqlalchemy import JSON, ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.public.estados_cidades import Cidade

from .base import Base


class Aerodromo(Base):
    __tablename__ = 'aerodromos'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    nome: Mapped[str] = mapped_column(nullable=False)
    codigo_icao: Mapped[str] = mapped_column(nullable=False, unique=True)
    codigo_iata: Mapped[str | None] = mapped_column(nullable=True)
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    elevacao: Mapped[float] = mapped_column(nullable=False)
    pais: Mapped[str] = mapped_column(nullable=False)
    utc: Mapped[int] = mapped_column(nullable=False)
    base_aerea: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    codigo_cidade: Mapped[int | None] = mapped_column(
        ForeignKey(Cidade.codigo), nullable=True
    )
    cidade_manual: Mapped[str | None] = mapped_column(nullable=True)

    # Relacionamento com Cidade
    cidade: Mapped[Cidade] = relationship(
        Cidade,
        lazy='selectin',
        backref='aerodromos',
        init=False,
        uselist=False,
    )
