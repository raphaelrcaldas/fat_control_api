from pydantic import BaseModel, ConfigDict, Field


class ProjetoCreate(BaseModel):
    id_projeto: str = Field(min_length=2, max_length=2)
    modelo: str = Field(min_length=1, max_length=20)


class ProjetoUpdate(BaseModel):
    modelo: str = Field(min_length=1, max_length=20)


class ProjetoOut(BaseModel):
    id_projeto: str
    modelo: str

    model_config = ConfigDict(from_attributes=True)


class TenantProjetoCreate(BaseModel):
    projeto: str = Field(min_length=2, max_length=2)
