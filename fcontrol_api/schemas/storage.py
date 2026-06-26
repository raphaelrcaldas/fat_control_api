from pydantic import BaseModel


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
