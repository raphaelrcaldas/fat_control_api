from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


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
    letra_finalidade: str | None = None
    data_realizacao: date | None = None
    validade_inspsau: date | None = None


class StorageStatsPublic(BaseModel):
    total_size: int
    total_objects: int


class BucketStatsPublic(BaseModel):
    name: str
    total_size: int
    total_objects: int


class AllBucketsStatsPublic(BaseModel):
    total_size: int
    total_objects: int
    buckets: list[BucketStatsPublic]


class AtaOrfaPublic(BaseModel):
    id: int
    user_id: int
    nome_guerra: str
    nome_completo: str
    file_name: str
    file_size: int
    created_at: datetime


class AtasOrfasResumo(BaseModel):
    total_atas: int
    total_size: int
    atas: list[AtaOrfaPublic]
