from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Estado(Base):
    __tablename__ = 'estados'

    codigo_uf: Mapped[int]
    nome: Mapped[str] = mapped_column(nullable=False)
    uf: Mapped[str] = mapped_column(primary_key=True)


class Cidade(Base):
    __tablename__ = 'cidades'

    codigo: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    nome: Mapped[str] = mapped_column(nullable=False)
    uf: Mapped[str] = mapped_column(ForeignKey('estados.uf'), nullable=False)


class GrupoLocEsp(Base):
    """Municipio classificado como localidade especial (GLE).

    `grupo` e inteiro por decisao de projeto: 1 = A, 2 = B. `fuso` e o
    offset UTC inteiro. Uma cidade e localidade especial uma unica vez —
    dai o unique em cidade_id.
    """

    __tablename__ = 'grupos_loc_esp'
    __table_args__ = (
        UniqueConstraint('cidade_id', name='uq_grupos_loc_esp_cidade'),
        CheckConstraint('grupo IN (1, 2)', name='ck_grupos_loc_esp_grupo'),
        CheckConstraint(
            'fuso BETWEEN -5 AND 0', name='ck_grupos_loc_esp_fuso'
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    cidade_id: Mapped[int] = mapped_column(ForeignKey(Cidade.codigo))
    grupo: Mapped[int] = mapped_column(nullable=False)
    fuso: Mapped[int] = mapped_column(nullable=False)

    cidade: Mapped[Cidade] = relationship('Cidade', init=False)
    icaos: Mapped[list['LocEspIcao']] = relationship(
        'LocEspIcao',
        back_populates='localidade',
        lazy='selectin',
        cascade='all, delete-orphan',
        init=False,
        default_factory=list,
    )


class LocEspIcao(Base):
    """Aerodromo que atende uma localidade especial.

    A ponte entre `etapas.origem`/`destino` (ICAO de 4 letras) e a
    localidade, que e chaveada por municipio IBGE. Sem ela nao ha JOIN
    possivel: a etapa nunca guarda o nome da cidade.

    Uma localidade tem N aerodromos (Manaus: SBEG e SBMN; Sao Gabriel da
    Cachoeira: SBUA, SBYA e SWMK), mas um aerodromo atende uma so
    localidade — dai o unique em icao.
    """

    __tablename__ = 'loc_esp_icao'
    __table_args__ = (
        UniqueConstraint('icao', name='uq_loc_esp_icao'),
        CheckConstraint("icao ~ '^[A-Z]{4}$'", name='ck_loc_esp_icao_formato'),
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    loc_esp_id: Mapped[int] = mapped_column(
        ForeignKey(GrupoLocEsp.id, ondelete='CASCADE')
    )
    icao: Mapped[str] = mapped_column(String(4), nullable=False)

    localidade: Mapped[GrupoLocEsp] = relationship(
        'GrupoLocEsp', back_populates='icaos', init=False
    )
