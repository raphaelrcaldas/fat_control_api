from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ProjetoAnv(Base):
    __tablename__ = 'projetos_anvs'

    id_projeto: Mapped[str] = mapped_column(String(10), primary_key=True)
    modelo: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True
    )


class Aeronave(Base):
    __tablename__ = 'aeronaves'

    matricula: Mapped[str] = mapped_column(String(4), primary_key=True)
    active: Mapped[bool]
    sit: Mapped[str] = mapped_column(String(2))
    obs: Mapped[str | None]
    projeto: Mapped[str] = mapped_column(
        String(10),
        ForeignKey(
            'projetos_anvs.id_projeto',
            onupdate='CASCADE',
            name='fk_aeronaves_projeto',
        ),
        default='C8',
        server_default='C8',
    )
    is_sim: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=None,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    proj: Mapped['ProjetoAnv'] = relationship(
        'ProjetoAnv', lazy='joined', init=False
    )
