from pydantic import BaseModel


class StorageStatsPublic(BaseModel):
    total_size: int
    total_objects: int


class BucketStatsPublic(BaseModel):
    name: str
    total_size: int
    total_objects: int
    # False quando a listagem do bucket falhou: os totais são 0 por falta
    # de leitura, não por o bucket estar vazio.
    readable: bool = True


class AllBucketsStatsPublic(BaseModel):
    total_size: int
    total_objects: int
    # Cota declarada em Settings.STORAGE_QUOTA_MB — o frontend não deve
    # cravar esse número, senão o farol de saturação vira ficção.
    quota_mb: int
    buckets: list[BucketStatsPublic]
