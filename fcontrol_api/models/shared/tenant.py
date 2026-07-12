from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .organizacao import Organizacao
from .users import User


class Tenant(Base):
    """Organização que é cliente da plataforma (tenant ativo).

    Subconjunto de `organizacoes`: a PK é compartilhada com o diretório
    universal (`organizacao_id` é PK e FK ao mesmo tempo). Apenas orgs
    registradas aqui podem ter vínculos de perfil/escopo na plataforma.
    """

    __tablename__ = 'tenants'

    organizacao_id: Mapped[str] = mapped_column(
        ForeignKey(
            'organizacoes.sigla', ondelete='RESTRICT', onupdate='CASCADE'
        ),
        primary_key=True,
    )
    active: Mapped[bool] = mapped_column(
        init=False, default=True, server_default=text('true')
    )
    # Tema de cor de marca (TemaEnum). String livre no banco; a validação
    # contra a lista fechada mora no schema Pydantic. Default 'red' = tema
    # padrão do produto.
    tema: Mapped[str] = mapped_column(
        String(20), default='red', server_default=text("'red'")
    )
    # Lema/saudação da unidade, exibida na tela de carregamento do client.
    # NOT NULL com default '': string vazia = org sem saudação definida
    # (o PATCH de tenant usa exclude_none, então limpar é enviar '').
    saudacao: Mapped[str] = mapped_column(
        String(120), default='', server_default=text("''")
    )
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )

    organizacao: Mapped[Organizacao] = relationship(
        Organizacao, lazy='selectin', init=False
    )


class TenantCargo(Base):
    """Titular de cada cargo institucional da org (assina documentos).

    Uma linha por (org, cargo) — a `UniqueConstraint` e o que garante o
    "um titular por cargo"; a troca de titular e um UPDATE do `user_id`.

    O titular e uma FK para `users` (nunca o nome/posto em texto): o
    documento renderiza `nome_completo`, `posto.mid` e `quadro` no momento
    da geracao, entao promocao e mudanca de comando se propagam sem
    reescrever nada. Nao ha vigencia historica: reimprimir um documento
    antigo mostra o titular *atual* (o documento e sempre emitido no
    presente).

    Cargo novo = novo valor em `CargoEnum` + linha aqui; sem migration.
    """

    __tablename__ = 'tenant_cargos'
    __table_args__ = (
        UniqueConstraint('uae', 'cargo', name='uq_tenant_cargo'),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True, init=False)
    uae: Mapped[str] = mapped_column(
        String(20),
        ForeignKey(
            'tenants.organizacao_id',
            ondelete='CASCADE',
            onupdate='CASCADE',
            name='fk_tenant_cargos_uae',
        ),
    )
    # CargoEnum. String livre no banco; a validacao contra a lista fechada
    # mora no schema Pydantic (mesmo contrato do `tema` acima).
    cargo: Mapped[str] = mapped_column(String(30))
    # RESTRICT: um militar que assina documentos nao pode ser removido sem
    # que o cargo seja reatribuido antes.
    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            'users.id',
            ondelete='RESTRICT',
            onupdate='CASCADE',
            name='fk_tenant_cargos_user',
        )
    )

    user: Mapped[User] = relationship(User, lazy='selectin', init=False)
