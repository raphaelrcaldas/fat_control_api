import asyncio
import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.organizacao import Organizacao
from fcontrol_api.models.shared.tenant import Tenant
from fcontrol_api.schemas.organizacao import (
    OrganizacaoCreate,
    OrganizacaoOut,
    OrganizacaoUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import require_system_admin
from fcontrol_api.services.brasao import (
    BRASAO_PREFIX,
    BUCKET_ORGANIZACOES,
    brasao_public_url,
)
from fcontrol_api.services.imagem import (
    ImagemInvalidaError,
    is_imagem_valida,
    normalizar_jpeg,
)
from fcontrol_api.services.storage import (
    delete_file,
    upload_file,
)
from fcontrol_api.utils.responses import success_response

logger = logging.getLogger(__name__)

# Leitura (GET) liberada a qualquer autenticado — o client precisa do
# diretório de orgs (siglas/nomes). Mutações exigem admin de sistema.
router = APIRouter(prefix='/organizacoes')

Session = Annotated[AsyncSession, Depends(get_session)]

# Alias local do bucket (usado em upload/delete de brasão neste router).
BUCKET = BUCKET_ORGANIZACOES

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _to_public(org: Organizacao) -> OrganizacaoOut:
    """OrganizacaoOut com a URL pública do brasão preenchida."""
    data = OrganizacaoOut.model_validate(org)
    data.brasao_url = brasao_public_url(org.brasao_path)
    return data


@router.get('/', response_model=ApiResponse[list[OrganizacaoOut]])
async def list_organizacoes(session: Session):
    orgs = await session.scalars(
        select(Organizacao).order_by(Organizacao.sigla)
    )
    return success_response(data=[_to_public(o) for o in orgs])


@router.get('/{sigla}', response_model=ApiResponse[OrganizacaoOut])
async def get_organizacao(sigla: str, session: Session):
    org = await session.get(Organizacao, sigla)
    if not org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não encontrada',
        )
    return success_response(data=_to_public(org))


@router.post(
    '/',
    response_model=ApiResponse[OrganizacaoOut],
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_system_admin)],
)
async def create_organizacao(body: OrganizacaoCreate, session: Session):
    org = Organizacao(
        sigla=body.sigla,
        sigla_2=body.sigla_2,
        sigla_3=body.sigla_3,
        nome=body.nome,
        alias=body.alias,
    )
    session.add(org)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Já existe uma organização com uma dessas siglas',
        )
    await session.refresh(org)
    return success_response(
        data=_to_public(org),
        message='Organização cadastrada com sucesso',
    )


@router.put(
    '/{sigla}',
    response_model=ApiResponse[OrganizacaoOut],
    dependencies=[Depends(require_system_admin)],
)
async def update_organizacao(
    sigla: str, body: OrganizacaoUpdate, session: Session
):
    org = await session.get(Organizacao, sigla)
    if not org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não encontrada',
        )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Já existe uma organização com uma dessas siglas',
        )
    await session.refresh(org)
    return success_response(
        data=_to_public(org),
        message='Organização atualizada com sucesso',
    )


@router.delete(
    '/{sigla}',
    response_model=ApiResponse[None],
    dependencies=[Depends(require_system_admin)],
)
async def delete_organizacao(sigla: str, session: Session):
    org = await session.get(Organizacao, sigla)
    if not org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não encontrada',
        )

    # FK RESTRICT em tenants.organizacao_id: não dá para remover do
    # diretório uma org que é cliente da plataforma. Antecipa erro amigável.
    tenant = await session.get(Tenant, sigla)
    if tenant:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Organização é um tenant da plataforma. Descadastre o '
                'tenant antes de removê-la do diretório.'
            ),
        )

    await session.delete(org)
    await session.commit()
    return success_response(message='Organização removida com sucesso')


@router.post(
    '/{sigla}/brasao',
    response_model=ApiResponse[OrganizacaoOut],
    dependencies=[Depends(require_system_admin)],
)
async def upload_brasao(sigla: str, file: UploadFile, session: Session):
    """Faz upload (JPG/PNG normalizado p/ JPEG) do brasão da organização."""
    org = await session.get(Organizacao, sigla)
    if not org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não encontrada',
        )

    # Rejeita pelo tamanho declarado no multipart ANTES de ler o corpo
    # (evita carregar um arquivo gigante em memória). O len() após o read
    # continua como backstop — `size` pode vir None de clientes atípicos.
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Arquivo excede o limite de 5 MB',
        )
    conteudo = await file.read()
    if len(conteudo) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Arquivo excede o limite de 5 MB',
        )
    if not is_imagem_valida(conteudo):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Arquivo não é uma imagem JPG/PNG válida',
        )

    try:
        conteudo = await asyncio.to_thread(normalizar_jpeg, conteudo)
    except ImagemInvalidaError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(e),
        ) from e
    tamanho = len(conteudo)

    key_antiga = org.brasao_path
    timestamp = datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')
    path = f'{BRASAO_PREFIX}/{sigla}/{timestamp}.jpg'

    # boto3 é síncrono (rede): despacha p/ thread pool para não travar o
    # event loop durante o upload (mesmo padrão de aeromedica/atas.py).
    await asyncio.to_thread(
        upload_file,
        bucket=BUCKET,
        path=path,
        data=conteudo,
        content_type='image/jpeg',
        size=tamanho,
    )
    org.brasao_path = path

    # Rollback storage↔banco: se o commit falhar, o objeto recém-enviado
    # fica órfão no bucket — removemos antes de propagar o erro.
    try:
        await session.commit()
    except Exception:
        logger.exception('Erro ao salvar brasão da organização no banco')
        await asyncio.to_thread(delete_file, BUCKET, path)
        raise

    await session.refresh(org)

    # Após persistir a nova key, remove a antiga (tolerando falha, para não
    # quebrar o fluxo se o objeto físico já não existir).
    if key_antiga and key_antiga != path:
        try:
            await asyncio.to_thread(delete_file, BUCKET, key_antiga)
        except Exception:
            logger.warning('Falha ao remover brasão antigo %s', key_antiga)

    return success_response(
        data=_to_public(org),
        message='Brasão atualizado com sucesso',
    )


@router.delete(
    '/{sigla}/brasao',
    response_model=ApiResponse[OrganizacaoOut],
    dependencies=[Depends(require_system_admin)],
)
async def delete_brasao(sigla: str, session: Session):
    """Remove o brasão da organização (banco + objeto no storage)."""
    org = await session.get(Organizacao, sigla)
    if not org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não encontrada',
        )

    key = org.brasao_path
    if not key:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não possui brasão',
        )

    org.brasao_path = None
    await session.commit()
    await session.refresh(org)

    # Objeto físico removido após o banco: se falhar, fica órfão no bucket
    # (tolerado — o vínculo lógico já não existe).
    try:
        await asyncio.to_thread(delete_file, BUCKET, key)
    except Exception:
        logger.warning('Falha ao remover brasão %s do storage', key)

    return success_response(
        data=_to_public(org),
        message='Brasão removido com sucesso',
    )
