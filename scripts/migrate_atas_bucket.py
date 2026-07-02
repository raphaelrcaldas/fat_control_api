"""
Migração do storage das atas de inspeção de saúde para bucket-por-domínio.

Modelo final: cada domínio tem seu próprio bucket. As atas vivem no bucket
`aeromedica` sob a sub-pasta `atas-inspecao/` — key
`atas-inspecao/{user_id}/{ts}_{nome}.pdf`. O `file_path` no banco guarda só
a key (sem o nome do bucket).

Fonte da verdade dos arquivos: o bucket ORIGINAL `atas-inspecao` (criado lá
no começo), cujos objetos estão intactos com key `{user_id}/{ts}_{nome}.pdf`.
Este script sempre copia DE LÁ, então é seguro re-rodar mesmo depois de uma
migração intermediária anterior.

O que faz, por ata (tabela `atas_inspecao`):
  1. Deriva a `base` = `{user_id}/{ts}_{nome}.pdf` a partir do `file_path`
     atual (tolera os formatos intermediários `aeromedica/atas-inspecao/base`
     e o original `base`).
  2. Copia `atas-inspecao/{base}` (bucket original) → `aeromedica` na key
     `atas-inspecao/{base}` (download + upload, à prova de S3-compat sem
     CopyObject entre buckets).
  3. Atualiza `file_path` para `atas-inspecao/{base}`.
  4. (Opcional, --delete-source) remove o objeto do bucket original.

Idempotente: registros cujo `file_path` já é `atas-inspecao/...` são pulados;
objetos já presentes no destino não são recopiados.

⚠️  Confira `api/.env` antes de rodar — STORAGE_* e DATABASE_URL ativos
    determinam contra qual storage/banco a migração roda (dev x PROD).

Uso:
    cd /path/to/api

    # 1) Simulação (não escreve nada), confira o relatório:
    uv run python scripts/migrate_atas_bucket.py

    # 2) Aplicar de fato (copia objetos + atualiza o banco):
    uv run python scripts/migrate_atas_bucket.py --apply

    # 3) Aplicar e remover os objetos do bucket original após copiar:
    uv run python scripts/migrate_atas_bucket.py --apply --delete-source
"""

import argparse
import asyncio

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from fcontrol_api.models.aeromedica.atas import AtaInspecao
from fcontrol_api.routers.aeromedica.atas import ATAS_PREFIX, BUCKET
from fcontrol_api.settings import Settings

# Bucket original (criado no início; guarda os PDFs intactos na raiz). É a
# fonte da verdade dos arquivos e o backup até rodar com --delete-source.
SOURCE_BUCKET = 'atas-inspecao'

# Prefixos intermediários já usados, para derivar a `base` do file_path atual.
_KNOWN_PREFIXES = (
    f'{BUCKET}/{ATAS_PREFIX}/',  # ex.: aeromedica/atas-inspecao/{base}
    f'{ATAS_PREFIX}/',  # alvo final: atas-inspecao/{base}
)


def _build_client():
    """Client S3 com as mesmas credenciais/endpoint da aplicação."""
    s = Settings()
    protocol = 'https' if s.STORAGE_SECURE else 'http'
    return boto3.client(
        's3',
        endpoint_url=f'{protocol}://{s.STORAGE_ENDPOINT}',
        aws_access_key_id=s.STORAGE_ACCESS_KEY,
        aws_secret_access_key=s.STORAGE_SECRET_KEY,
        region_name=s.STORAGE_REGION,
        config=Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
        ),
    )


def _base_key(file_path: str) -> str:
    """Extrai `{user_id}/{ts}_{nome}.pdf` de qualquer formato de file_path."""
    for prefix in _KNOWN_PREFIXES:
        if file_path.startswith(prefix):
            return file_path[len(prefix) :]
    return file_path  # formato original (sem prefixo)


def _object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response['Error']['Code'] in {'404', 'NoSuchKey', 'NotFound'}:
            return False
        raise
    return True


def _ensure_bucket(client, bucket: str, *, apply: bool) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        return
    except ClientError as e:
        code = e.response['Error']['Code']
        if code not in {'404', 'NoSuchBucket', 'NotFound'}:
            # 403 etc.: bucket existe mas head negado — segue.
            return
    print(f'   ↳ bucket destino "{bucket}" inexistente', end='')
    if apply:
        client.create_bucket(Bucket=bucket)
        print(' → criado')
    else:
        print(' (seria criado)')


async def migrar(apply: bool, delete_source: bool) -> None:
    target_prefix = f'{ATAS_PREFIX}/'
    print('=' * 80)
    print('MIGRAÇÃO DO STORAGE DAS ATAS (bucket-por-domínio)')
    print(f'  origem : bucket "{SOURCE_BUCKET}" (key na raiz)')
    print(f'  destino: bucket "{BUCKET}" sob "{target_prefix}"')
    print(f'  modo   : {"APLICAR" if apply else "DRY-RUN (simulação)"}')
    if apply and delete_source:
        print('  extra  : remover objeto do bucket original após copiar')
    print('=' * 80)
    print()

    client = _build_client()
    _ensure_bucket(client, BUCKET, apply=apply)
    print()

    engine = create_async_engine(Settings().DATABASE_URL)
    async_session = AsyncSession(engine, expire_on_commit=False)

    migradas = puladas = erros = 0

    async with async_session as session:
        atas = (await session.execute(select(AtaInspecao))).scalars().all()
        print(f'📋 Atas no banco: {len(atas)}')
        print()

        for ata in atas:
            base = _base_key(ata.file_path)
            new_key = f'{target_prefix}{base}'

            # Já no formato final E objeto presente no destino → nada a fazer.
            if ata.file_path == new_key and _object_exists(
                client, BUCKET, new_key
            ):
                puladas += 1
                print(f'  ⏭️  #{ata.id} já migrada ({new_key})')
                continue

            try:
                if _object_exists(client, BUCKET, new_key):
                    print(f'  ↪️  #{ata.id} já no destino, atualiza só o DB')
                else:
                    if apply:
                        obj = client.get_object(Bucket=SOURCE_BUCKET, Key=base)
                        body = obj['Body'].read()
                        content_type = obj.get(
                            'ContentType', 'application/pdf'
                        )
                        client.put_object(
                            Bucket=BUCKET,
                            Key=new_key,
                            Body=body,
                            ContentType=content_type,
                        )
                    print(f'  ✅ #{ata.id}  {base}  →  {BUCKET}/{new_key}')

                if apply:
                    ata.file_path = new_key

                if apply and delete_source:
                    client.delete_object(Bucket=SOURCE_BUCKET, Key=base)

                migradas += 1
            except ClientError:
                erros += 1
                print(f'  ❌ #{ata.id} falhou (base={base})', flush=True)
                import traceback  # noqa: PLC0415

                traceback.print_exc()

        if apply and erros == 0:
            await session.commit()
            print('\n💾 Banco atualizado (commit).')
        elif apply:
            await session.rollback()
            print('\n⚠️  Houve erros — rollback do banco. Nada foi gravado.')

    await engine.dispose()

    print()
    print('=' * 80)
    print(f'  migradas: {migradas}   já-migradas: {puladas}   erros: {erros}')
    if not apply:
        print('  (DRY-RUN: nenhum objeto copiado, nenhum registro alterado)')
    print('=' * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Aplica a migração. Sem esta flag, roda em modo simulação.',
    )
    parser.add_argument(
        '--delete-source',
        action='store_true',
        help='Remove o objeto do bucket original após copiá-lo (só --apply).',
    )
    args = parser.parse_args()
    asyncio.run(migrar(apply=args.apply, delete_source=args.delete_source))


if __name__ == '__main__':
    main()
