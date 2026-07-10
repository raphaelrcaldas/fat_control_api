from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DadosExtraidos(BaseModel):
    nome_completo: str | None = None
    letra_finalidade: str | None = None
    data_realizacao: date | None = None
    validade_inspsau: date | None = None


class AtaInspecaoPublic(BaseModel):
    id: int
    user_id: int
    file_path: str
    file_name: str
    file_size: int
    letra_finalidade: str | None = None
    data_realizacao: date | None = None
    validade_inspsau: date | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AtaInspecaoWithUrl(AtaInspecaoPublic):
    url: str


class AtaUploadResponse(BaseModel):
    ata: AtaInspecaoPublic
    dados_extraidos: DadosExtraidos
    cemal_atualizado: bool = False
    extracao_vazia: bool = False


class AtaExtrairResponse(BaseModel):
    dados_extraidos: DadosExtraidos
    extracao_vazia: bool = False


class AtaUpdate(BaseModel):
    letra_finalidade: str | None = Field(default=None, max_length=1)
    data_realizacao: date | None = None
    validade_inspsau: date | None = None
