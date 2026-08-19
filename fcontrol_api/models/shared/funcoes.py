from sqlalchemy import (
    ForeignKey,
    Identity,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Funcao(Base):
    """Catálogo de funções de tripulante.

    O conjunto de códigos é doutrina (comum a toda a FAB), por isso a tabela
    é global: quem escolhe as funções que **opera** é cada unidade, em
    `funcoes_uae`. `cor` guarda só o nome do tema ('blue', 'amber'); o mapa
    nome → classe Tailwind mora no front, que não compila classe montada em
    runtime.
    """

    __tablename__ = 'funcoes'

    cod: Mapped[str] = mapped_column(String(3), primary_key=True)
    nome: Mapped[str] = mapped_column(String(40))
    nome_curto: Mapped[str] = mapped_column(String(20))
    cor: Mapped[str] = mapped_column(String(16))
    ordem: Mapped[int] = mapped_column(SmallInteger)
    # Função esporádica (mestre de lançamento, médico): sem controle de
    # posição a bordo.
    esporadica: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)

    posicoes: Mapped[list['FuncaoPosicao']] = relationship(
        'FuncaoPosicao',
        back_populates='funcao',
        lazy='selectin',
        order_by='FuncaoPosicao.ordem',
        init=False,
        default_factory=list,
    )


class FuncaoPosicao(Base):
    """Posição a bordo de uma função ('1P', 'IN', 'AC'...).

    Vive na função, não na org: a posição é atribuição doutrinária. O código
    NÃO é único global ('O3' é posição de `pil` e de `oe`), por isso a
    unicidade é (func_cod, cod) e `etapa.func_bordo` não tem FK.
    """

    __tablename__ = 'funcoes_posicoes'
    __table_args__ = (
        UniqueConstraint('func_cod', 'cod', name='uq_funcoes_posicoes_func'),
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    func_cod: Mapped[str] = mapped_column(
        ForeignKey('funcoes.cod', ondelete='CASCADE', onupdate='CASCADE')
    )
    cod: Mapped[str] = mapped_column(String(2))
    nome: Mapped[str] = mapped_column(String(40))
    ordem: Mapped[int] = mapped_column(SmallInteger)
    tipo: Mapped[str] = mapped_column(String(10), default='titular')
    descricao: Mapped[str | None] = mapped_column(String(80), default=None)

    funcao: Mapped[Funcao] = relationship(
        'Funcao', back_populates='posicoes', init=False
    )


class FuncaoUae(Base):
    """Funções que a unidade opera.

    Escopo por org no mesmo padrão de `tenant_projetos`: o cadastro de
    tripulante só oferece o que a unidade tem. `nome_custom` cobre a org que
    chama a função por outro nome sem duplicar o catálogo.
    """

    __tablename__ = 'funcoes_uae'
    __table_args__ = (
        UniqueConstraint('uae', 'func_cod', name='uq_funcoes_uae_uae_func'),
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    uae: Mapped[str] = mapped_column(
        ForeignKey(
            'tenants.organizacao_id',
            ondelete='RESTRICT',
            onupdate='CASCADE',
        )
    )
    func_cod: Mapped[str] = mapped_column(
        ForeignKey('funcoes.cod', ondelete='RESTRICT', onupdate='CASCADE')
    )
    nome_custom: Mapped[str | None] = mapped_column(String(40), default=None)
    ordem: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    active: Mapped[bool] = mapped_column(default=True)

    funcao: Mapped[Funcao] = relationship(
        'Funcao', lazy='selectin', init=False
    )
