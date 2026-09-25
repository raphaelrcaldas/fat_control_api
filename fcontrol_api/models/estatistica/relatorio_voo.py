from datetime import date, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Identity,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from fcontrol_api.models.shared.aeronaves import Aeronave
from fcontrol_api.models.shared.tenant import Tenant
from fcontrol_api.models.shared.users import User

from .base import Base


class RelatorioVoo(Base):
    """Relatório de voo escaneado (PDF), arquivado por aeronave e dia.

    `anv` e `data` dão nome ao objeto no bucket e por isso são imutáveis;
    `seq` diferencia vários relatórios da mesma aeronave no mesmo dia. Um
    número apagado no meio não é reaproveitado; nada é renumerado — só o
    maior `seq` do dia pode ser reusado pelo próximo envio.
    """

    __tablename__ = 'relatorios_voo'
    # O `Base` do schema define `{'schema': 'estatistica'}`; declarar
    # constraints substitui o atributo, então o dicionário vai no fim.
    __table_args__ = (
        UniqueConstraint(
            'uae', 'anv', 'data', 'seq', name='uq_relatorios_voo_dia_seq'
        ),
        UniqueConstraint('uae', 'sha256', name='uq_relatorios_voo_sha256'),
        {'schema': 'estatistica'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    uae: Mapped[str] = mapped_column(
        String(20),
        ForeignKey(
            Tenant.organizacao_id, ondelete='RESTRICT', onupdate='CASCADE'
        ),
    )
    anv: Mapped[str] = mapped_column(String(4), ForeignKey(Aeronave.matricula))
    data: Mapped[date]
    seq: Mapped[int] = mapped_column(SmallInteger)
    file_path: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey(User.id))
    num_paginas: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    obs: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
