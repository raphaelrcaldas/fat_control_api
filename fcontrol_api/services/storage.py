import logging
import threading
from functools import cache
from io import BytesIO

from botocore.exceptions import ClientError

from fcontrol_api.settings import Settings

logger = logging.getLogger(__name__)

# Flag + lock para garantir que a verificação/criação do bucket rode no
# máximo uma vez por processo, sem race condition sob threads concorrentes
# (FastAPI executa handlers síncronos em thread pool — múltiplos uploads
# simultâneos entrariam em ensure_bucket() ao mesmo tempo).
_bucket_verified = False
_bucket_lock = threading.Lock()


@cache
def _get_client():
    # Imports lazy: boto3/botocore são pesados (~300-500ms) e só devem
    # ser carregados quando o storage for efetivamente usado.
    import boto3  # noqa: PLC0415
    from botocore.config import Config  # noqa: PLC0415

    settings = Settings()
    protocol = 'https' if settings.STORAGE_SECURE else 'http'
    endpoint_url = f'{protocol}://{settings.STORAGE_ENDPOINT}'

    return boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.STORAGE_SECRET_KEY,
        region_name=settings.STORAGE_REGION,
        config=Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
            # connect_timeout curto: detecta storage fora do ar rápido.
            # read_timeout=30s é um compromisso — uploads de PDFs/atas
            # maiores precisam desse tempo sob rede lenta. Se o storage
            # estiver saudável mas a rede lenta, reduzir isso causaria
            # falsos negativos em uploads legítimos.
            connect_timeout=3,
            read_timeout=30,
            retries={'max_attempts': 2, 'mode': 'standard'},
        ),
    )


@cache
def _get_bucket() -> str:
    return Settings().STORAGE_BUCKET


def ensure_bucket() -> None:
    """Garante que o bucket existe. Idempotente e à prova de falhas.

    Chamado de forma lazy (primeira operação de escrita) — NÃO deve
    ser chamado no boot, para não acoplar disponibilidade do storage
    ao startup da API.
    """
    global _bucket_verified  # noqa: PLW0603
    if _bucket_verified:
        return

    with _bucket_lock:
        # Double-checked locking: outra thread pode ter verificado
        # enquanto esperávamos o lock.
        if _bucket_verified:
            return

        client = _get_client()
        bucket = _get_bucket()
        try:
            client.head_bucket(Bucket=bucket)
            _bucket_verified = True
        except ClientError as e:
            code = e.response['Error']['Code']
            if code == '404':
                try:
                    client.create_bucket(Bucket=bucket)
                    _bucket_verified = True
                except ClientError:
                    logger.exception('Falha ao criar bucket %s', bucket)
            elif code in {'403', 'AccessDenied', 'Forbidden'}:
                # 403 significa "bucket existe e você não tem permissão
                # de head" — situação comum em buckets provisionados por
                # admin. Consideramos verificado; operações reais dirão
                # se há problema de permissão por operação.
                logger.info(
                    'Bucket %s head negado (code=%s); assumindo que existe',
                    bucket,
                    code,
                )
                _bucket_verified = True
            else:
                # 5xx/timeouts/etc.: storage pode estar instável. NÃO
                # marcamos como verificado — tentamos de novo na próxima
                # operação (pode ter se recuperado). Log só; a operação
                # real abaixo vai falhar naturalmente se ainda quebrado.
                logger.warning(
                    'Bucket %s check falhou (code=%s); '
                    'seguir tentando na próxima operação',
                    bucket,
                    code,
                )
        except Exception:
            # Timeout, DNS, rede: idem acima — não marca verificado.
            logger.exception('Erro inesperado verificando bucket %s', bucket)


def upload_file(
    path: str,
    data: bytes,
    content_type: str,
    size: int,
) -> None:
    ensure_bucket()
    client = _get_client()
    bucket = _get_bucket()
    client.upload_fileobj(
        Fileobj=BytesIO(data),
        Bucket=bucket,
        Key=path,
        ExtraArgs={'ContentType': content_type},
    )


def get_signed_url(path: str, expires: int = 900) -> str:
    client = _get_client()
    bucket = _get_bucket()
    return client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': path},
        ExpiresIn=expires,
    )


def delete_file(path: str) -> None:
    client = _get_client()
    bucket = _get_bucket()
    client.delete_object(Bucket=bucket, Key=path)


def get_bucket_stats() -> dict:
    client = _get_client()
    bucket = _get_bucket()
    total_size = 0
    total_objects = 0

    try:
        paginator = client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get('Contents', []):
                total_size += obj.get('Size', 0)
                total_objects += 1
    except ClientError:
        logger.exception('Erro ao listar objetos do bucket')

    return {
        'total_size': total_size,
        'total_objects': total_objects,
    }


def get_all_buckets_stats() -> dict:
    client = _get_client()
    total_size = 0
    total_objects = 0
    buckets_stats: list[dict] = []

    try:
        response = client.list_buckets()
        for bucket in response.get('Buckets', []):
            bucket_name = bucket['Name']
            bucket_size = 0
            bucket_objects = 0

            try:
                paginator = client.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=bucket_name):
                    for obj in page.get('Contents', []):
                        bucket_size += obj.get('Size', 0)
                        bucket_objects += 1
            except ClientError:
                logger.warning(
                    'Erro ao listar objetos do bucket %s',
                    bucket_name,
                )

            buckets_stats.append({
                'name': bucket_name,
                'total_size': bucket_size,
                'total_objects': bucket_objects,
            })
            total_size += bucket_size
            total_objects += bucket_objects
    except ClientError:
        logger.exception('Erro ao listar buckets do storage')

    return {
        'total_size': total_size,
        'total_objects': total_objects,
        'buckets': buckets_stats,
    }
