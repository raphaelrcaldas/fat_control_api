import asyncio
import logging
from http import HTTPStatus

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException

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
from fcontrol_api.settings import Settings
from fcontrol_api.utils.responses import success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/storage', tags=['Storage'])

STORAGE_UNAVAILABLE = 'Storage indisponível: não foi possível ler o serviço.'


@router.get(
    '/stats',
    response_model=ApiResponse[StorageStatsPublic],
)
async def storage_stats(bucket: str, prefix: str | None = None):
    """Estatisticas de uso de um bucket.

    `bucket` e obrigatorio (cada dominio tem o seu). Informe `prefix` para
    escopar a um subconjunto; sem `prefix`, conta o bucket todo.
    """
    try:
        stats = await asyncio.to_thread(get_bucket_stats, bucket, prefix)
    except (ClientError, BotoCoreError) as e:
        # 502 e não 200-com-zeros: o consumidor precisa distinguir
        # "bucket vazio" de "não consegui perguntar".
        logger.exception('Falha ao ler stats do bucket %s', bucket)
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=STORAGE_UNAVAILABLE,
        ) from e

    return success_response(
        data=StorageStatsPublic(**stats),
    )


@router.get(
    '/all',
    response_model=ApiResponse[AllBucketsStatsPublic],
)
async def all_buckets_stats():
    """Retorna estatisticas de todos os buckets do storage."""
    try:
        stats = await asyncio.to_thread(get_all_buckets_stats)
    except (ClientError, BotoCoreError) as e:
        logger.exception('Falha ao listar buckets do storage')
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=STORAGE_UNAVAILABLE,
        ) from e

    buckets = [BucketStatsPublic(**b) for b in stats['buckets']]
    return success_response(
        data=AllBucketsStatsPublic(
            total_size=stats['total_size'],
            total_objects=stats['total_objects'],
            quota_mb=Settings().STORAGE_QUOTA_MB,
            buckets=buckets,
        ),
    )
