import asyncio
import logging
from http import HTTPStatus

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException

from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.storage import (
    AllBucketsStatsPublic,
    BucketStatsPublic,
)
from fcontrol_api.security import require_system_admin
from fcontrol_api.services.storage import get_all_buckets_stats
from fcontrol_api.settings import Settings
from fcontrol_api.utils.responses import success_response

logger = logging.getLogger(__name__)

# Uso do storage é de TODO o sistema (nomes e tamanhos de todos os buckets,
# de todas as orgs): só o admin de sistema, como o resto do grupo /admin.
router = APIRouter(
    prefix='/storage',
    tags=['Storage'],
    dependencies=[Depends(require_system_admin)],
)

STORAGE_UNAVAILABLE = 'Storage indisponível: não foi possível ler o serviço.'


@router.get(
    '/all',
    response_model=ApiResponse[AllBucketsStatsPublic],
)
async def all_buckets_stats():
    """Retorna estatisticas de todos os buckets do storage."""
    try:
        stats = await asyncio.to_thread(get_all_buckets_stats)
    except (ClientError, BotoCoreError) as e:
        # 502 e não 200-com-zeros: o consumidor precisa distinguir
        # "storage vazio" de "não consegui perguntar".
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
