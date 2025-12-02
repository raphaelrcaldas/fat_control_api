from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.cidade import CidadeSchema


class BaseAerea(BaseModel):
    """Schema para informações de base aérea armazenadas como JSON"""

    nome: str = Field(..., description='Nome da base aérea')
    sigla: str = Field(
        ..., min_length=4, max_length=4, description='Sigla da base aérea'
    )

    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'nome': 'Base Aérea de Brasília',
                'sigla': 'BABR',
            }
        }
    )


class AerodromoCreate(BaseModel):
    nome: str
    codigo_icao: str = Field(..., min_length=4, max_length=4)
    codigo_iata: str | None = Field(None, min_length=3, max_length=3)
    latitude: float
    longitude: float
    elevacao: float
    pais: str
    utc: int
    base_aerea: BaseAerea | None = None
    codigo_cidade: int | None = None
    cidade_manual: str | None = None


class AerodromoUpdate(BaseModel):
    nome: str | None = None
    codigo_icao: str | None = Field(None, min_length=4, max_length=4)
    codigo_iata: str | None = Field(None, min_length=3, max_length=3)
    latitude: float | None = None
    longitude: float | None = None
    elevacao: float | None = None
    pais: str | None = None
    utc: int | None = None
    base_aerea: BaseAerea | None = None
    codigo_cidade: int | None = None
    cidade_manual: str | None = None


class AerodromoPublic(BaseModel):
    id: int
    nome: str
    codigo_icao: str
    codigo_iata: str | None
    latitude: float
    longitude: float
    elevacao: float
    pais: str
    utc: int
    base_aerea: BaseAerea | None
    cidade_manual: str | None
    codigo_cidade: int | None
    cidade: CidadeSchema | None

    model_config = ConfigDict(from_attributes=True)
