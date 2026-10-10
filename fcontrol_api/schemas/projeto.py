from pydantic import BaseModel, ConfigDict, Field, field_validator


def _caixa_alta(v):
    # Projeto e modelo são siglas exibidas como estão (`C8`, `KC-390`).
    return v.strip().upper() if isinstance(v, str) else v


class ProjetoCreate(BaseModel):
    id_projeto: str = Field(min_length=2, max_length=2)
    modelo: str = Field(min_length=1, max_length=20)

    _normaliza = field_validator('id_projeto', 'modelo', mode='before')(
        _caixa_alta
    )


class ProjetoUpdate(BaseModel):
    modelo: str = Field(min_length=1, max_length=20)

    _normaliza = field_validator('modelo', mode='before')(_caixa_alta)


class ProjetoOut(BaseModel):
    id_projeto: str
    modelo: str

    model_config = ConfigDict(from_attributes=True)


class TenantProjetoCreate(BaseModel):
    projeto: str = Field(min_length=2, max_length=2)
