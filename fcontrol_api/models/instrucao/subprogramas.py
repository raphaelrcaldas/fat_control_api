from datetime import date

from sqlalchemy import (
    ForeignKey,
    Identity,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.shared.funcoes import Funcao
from fcontrol_api.models.shared.tenant import Tenant
from fcontrol_api.models.shared.tripulantes import Tripulante

from .base import Base


class Subprograma(Base):
    """Subprograma de instrucao da unidade (ex.: SPFO-01).

    Escopado por `uae`: o codigo e unico dentro da unidade, nao globalmente —
    duas unidades podem ter um SPFO-01 com ementas diferentes. `func` aponta
    para o catalogo global de funcoes, mas a rota so aceita funcao que a
    unidade opera (`funcoes_uae`), mesmo padrao do `proj`/`tenant_projetos`.
    """

    __tablename__ = 'subprogramas'
    __table_args__ = (
        UniqueConstraint('uae', 'codigo', name='uq_subprogramas_uae_codigo'),
        {'schema': 'instrucao'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    uae: Mapped[str] = mapped_column(
        ForeignKey(
            Tenant.organizacao_id, ondelete='RESTRICT', onupdate='CASCADE'
        )
    )
    codigo: Mapped[str] = mapped_column(String(7))
    descricao: Mapped[str] = mapped_column(String(120))
    # 'Formacao' | 'Manutencao' | 'Especializacao' — doutrina, nao varia por
    # unidade. O banco guarda o proprio rotulo (com acento) para que o front
    # exiba sem mapa nenhum; a lista fechada vive no schema Pydantic.
    tipo: Mapped[str] = mapped_column(String(20))
    func: Mapped[str] = mapped_column(
        ForeignKey(Funcao.cod, onupdate='CASCADE', name='fk_subprogramas_func')
    )
    observacoes: Mapped[str | None] = mapped_column(Text, default=None)


class Paop(Base):
    """Plano Anual de Operacao e Preparo: cabecalho anual da unidade.

    A janela vive so aqui: o PAOP pode nao cobrir o ano civil inteiro
    (unidade que ativa o plano no meio do ano), mas os subprogramas do plano
    compartilham a mesma vigencia. O default de ano civil e aplicado na rota,
    nao no banco.
    """

    __tablename__ = 'paops'
    __table_args__ = (
        UniqueConstraint('uae', 'ano', name='uq_paops_uae_ano'),
        {'schema': 'instrucao'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    uae: Mapped[str] = mapped_column(
        ForeignKey(
            Tenant.organizacao_id, ondelete='RESTRICT', onupdate='CASCADE'
        )
    )
    ano: Mapped[int] = mapped_column(SmallInteger)
    data_ini: Mapped[date]
    data_fim: Mapped[date]
    status: Mapped[str] = mapped_column(String(12), default='rascunho')

    subprogramas: Mapped[list['PaopSubprograma']] = relationship(
        'PaopSubprograma',
        back_populates='paop',
        lazy='selectin',
        cascade='all, delete-orphan',
        init=False,
        default_factory=list,
    )


class PaopSubprograma(Base):
    """Subprograma incluido em um PAOP."""

    __tablename__ = 'paop_subprogramas'
    __table_args__ = (
        UniqueConstraint(
            'paop_id', 'subprograma_id', name='uq_paop_subprogramas'
        ),
        {'schema': 'instrucao'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    paop_id: Mapped[int] = mapped_column(
        ForeignKey(Paop.id, ondelete='CASCADE')
    )
    subprograma_id: Mapped[int] = mapped_column(
        ForeignKey(Subprograma.id, ondelete='RESTRICT')
    )

    paop: Mapped[Paop] = relationship(
        'Paop', back_populates='subprogramas', init=False
    )
    subprograma: Mapped[Subprograma] = relationship(
        'Subprograma', lazy='selectin', init=False
    )
    tripulantes: Mapped[list['TripulanteSubprograma']] = relationship(
        'TripulanteSubprograma',
        back_populates='paop_subprograma',
        lazy='selectin',
        cascade='all, delete-orphan',
        init=False,
        default_factory=list,
    )


class TripulanteSubprograma(Base):
    """Tripulante matriculado em um subprograma do PAOP.

    So o vinculo: acompanhamento (situacao, conclusao) nao entra neste corte.
    """

    __tablename__ = 'tripulante_subprogramas'
    __table_args__ = (
        UniqueConstraint(
            'paop_subprograma_id',
            'trip_id',
            name='uq_tripulante_subprogramas',
        ),
        {'schema': 'instrucao'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    paop_subprograma_id: Mapped[int] = mapped_column(
        ForeignKey(PaopSubprograma.id, ondelete='CASCADE')
    )
    trip_id: Mapped[int] = mapped_column(
        ForeignKey(Tripulante.id, ondelete='CASCADE')
    )
    data_inclusao: Mapped[date]

    paop_subprograma: Mapped[PaopSubprograma] = relationship(
        'PaopSubprograma', back_populates='tripulantes', init=False
    )
