from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.cidade import CidadeSchema
from fcontrol_api.schemas.etiquetas import EtiquetaSchema
from fcontrol_api.schemas.users import UserPublic


class MissoesFilterParams(BaseModel):
    """
    Parâmetros de filtro e paginação para missões.

    Validação de entrada para prevenir SQL injection e DoS attacks.
    Todos os parâmetros são opcionais exceto page e per_page.
    """

    tipo_doc: Optional[str] = Field(
        None, max_length=10, description="Tipo do documento (ex: 'BI', 'OM')"
    )

    n_doc: Optional[int] = Field(None, ge=1, description='Número do documento')

    tipo: Optional[str] = Field(
        None, max_length=10, description='Tipo da missão'
    )

    user_search: Optional[str] = Field(
        None,
        max_length=100,
        description='Nome de guerra para busca (busca parcial)',
    )

    city: Optional[str] = Field(
        None, max_length=100, description='Nome da cidade (busca parcial)'
    )

    ini: Optional[date] = Field(
        None, description='Data inicial de afastamento (filtro >= ini)'
    )

    fim: Optional[date] = Field(
        None, description='Data final de regresso (filtro <= fim)'
    )

    etiqueta_ids: Optional[str] = Field(
        None,
        pattern=r'^[\d,\s]+$',
        max_length=200,
        description="IDs de etiquetas separados por vírgula (ex: '1,2,3')",
    )

    page: int = Field(1, ge=1, description='Número da página (inicia em 1)')

    per_page: int = Field(
        20,
        ge=1,
        le=100,
        description='Itens por página (máximo 100 para prevenir DoS)',
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class PernoiteFragMis(BaseModel):
    id: Optional[int] = None
    frag_id: Optional[int] = None
    acrec_desloc: bool
    data_ini: date
    data_fim: date
    meia_diaria: bool
    obs: str
    cidade_id: int
    cidade: CidadeSchema
    model_config = ConfigDict(from_attributes=True)


class UserFragMis(BaseModel):
    id: Optional[int] = None
    frag_id: Optional[int] = None
    user_id: int
    p_g: PostoGradEnum
    sit: str
    user: UserPublic

    model_config = ConfigDict(from_attributes=True)


class FragMisSchema(BaseModel):
    id: Optional[int] = None
    n_doc: int
    tipo_doc: str
    indenizavel: bool
    acrec_desloc: bool
    afast: datetime
    regres: datetime
    desc: str
    obs: str
    tipo: str
    pernoites: list[PernoiteFragMis]
    users: list[UserFragMis]
    etiquetas: list[EtiquetaSchema] = []
    custos: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)
