import logging
from functools import lru_cache
from io import BytesIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from fcontrol_api.settings import Settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_client():
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
        ),
    )


@lru_cache(maxsize=1)
def _get_bucket() -> str:
    return Settings().STORAGE_BUCKET


def ensure_bucket() -> None:
    client = _get_client()
    bucket = _get_bucket()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as e:
        code = e.response['Error']['Code']
        if code == '404':
            client.create_bucket(Bucket=bucket)
        else:
            logger.warning(
                'Bucket %s check failed (code=%s), assuming it exists',
                bucket,
                code,
            )


def upload_file(
    path: str,
    data: bytes,
    content_type: str,
    size: int,
) -> None:
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
