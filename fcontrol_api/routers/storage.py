import asyncio

from fastapi import APIRouter

from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.storage import (
    AllBucketsStatsPublic,
    BucketStatsPublic,
    StorageStatsPublic,
)
from fcontrol_api.services.storage import (
    get_all_buckets_stats,
    get_bucket_stats,
)
from fcontrol_api.utils.responses import success_response

router = APIRouter(prefix='/storage', tags=['Storage'])


@router.get(
    '/stats',
    response_model=ApiResponse[StorageStatsPublic],
)
async def storage_stats(bucket: str, prefix: str | None = None):
    """Estatisticas de uso de um bucket.

    `bucket` e obrigatorio (cada dominio tem o seu). Informe `prefix` para
    escopar a um subconjunto; sem `prefix`, conta o bucket todo.
    """
    stats = await asyncio.to_thread(get_bucket_stats, bucket, prefix)
    return success_response(
        data=StorageStatsPublic(**stats),
    )


@router.get(
    '/all',
    response_model=ApiResponse[AllBucketsStatsPublic],
)
async def all_buckets_stats():
    """Retorna estatisticas de todos os buckets do storage."""
    stats = await asyncio.to_thread(get_all_buckets_stats)
    buckets = [BucketStatsPublic(**b) for b in stats['buckets']]
    return success_response(
        data=AllBucketsStatsPublic(
            total_size=stats['total_size'],
            total_objects=stats['total_objects'],
            buckets=buckets,
        ),
    )
