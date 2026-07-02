import asyncio
import logging
import unicodedata
from datetime import UTC, datetime
from enum import Enum
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.inteligencia.passaportes import Passaporte
from fcontrol_api.models.shared.funcoes import Funcao
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.inteligencia.passaportes import (
    ImagemOrfaPublic,
    ImagensOrfasDelete,
    ImagensOrfasDeleteResponse,
    ImagensOrfasResumo,
    PassaportePublic,
    PassaporteUpdate,
    TripPassaporteOut,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrgOptional,
    ensure_org_permission_or_owner,
    get_current_user,
    has_org_permission,
    permission_checker,
)
from fcontrol_api.services.imagem import (
    ImagemInvalidaError,
    is_imagem_valida,
    normalizar_jpeg,
)
from fcontrol_api.services.storage import (
    delete_file,
    get_signed_url,
    upload_file,
)
from fcontrol_api.utils.responses import success_response

logger = logging.getLogger(__name__)

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/passaportes', tags=['Inteligencia'])

# Guardas reutilizáveis do recurso `passaportes`. O upsert (PUT) resolve
# create-vs-update no handler, então não tem alias (ver has_org_permission).
ViewPassaportes = Depends(permission_checker('passaportes', 'view'))
DeletePassaportes = Depends(permission_checker('passaportes', 'delete'))

# As imagens (passaporte/visto) são um recurso próprio `passaporte.image`,
# com suas 4 ações granulares — desacopladas dos dados textuais do
# passaporte. `view` é checado inline nos GETs (inclui as URLs só para quem
# pode ver a imagem); `delete` tem alias; o upload resolve create-vs-update
# no handler (ver has_org_permission).
IMG_RESOURCE = 'passaporte.image'
DeleteImgPassaporte = Depends(permission_checker(IMG_RESOURCE, 'delete'))

# Bucket do domínio inteligência. O nome do bucket é constante de código
# (não é env/secret) — cada domínio tem o seu. Ver services/storage.py.
BUCKET = 'inteligencia'

# Sub-pastas (prefixos de key) das imagens dentro do bucket do domínio,
# isolando passaporte de visto.
PASSAPORTE_PREFIX = 'passaporte'
VISA_PREFIX = 'visa'

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class TipoImagem(str, Enum):
    """Tipo de imagem do registro de passaporte (gera 422 limpo)."""

    passaporte = 'passaporte'
    visa = 'visa'


def _signed_url_opt(key: str | None) -> str | None:
    """URL assinada da `key` no bucket do domínio, ou None se sem key."""
    return get_signed_url(BUCKET, key) if key else None


def _to_public(
    passaporte: Passaporte, with_urls: bool = True
) -> PassaportePublic:
    """PassaportePublic; com `with_urls=False` omite as signed URLs.

    As URLs só são expostas a quem tem `passaporte.image.view` (os GETs
    passam o resultado da checagem; os endpoints de escrita, sendo o próprio
    ator da operação, sempre as incluem).
    """
    data = PassaportePublic.model_validate(passaporte)
    if with_urls:
        data.passaporte_url = _signed_url_opt(passaporte.passaporte_file_path)
        data.visa_url = _signed_url_opt(passaporte.visa_file_path)
    return data


def _nome_ascii(nome_guerra: str) -> str:
    """Normaliza o nome de guerra para um slug ASCII de nome de arquivo."""
    nome = nome_guerra.strip().replace(' ', '_').lower()
    return ''.join(
        c
        for c in unicodedata.normalize('NFD', nome)
        if unicodedata.category(c) != 'Mn'
    )


@router.get(
    '/',
    response_model=ApiResponse[list[TripPassaporteOut]],
)
async def list_passaportes(
    session: Session,
    user: Annotated[User, ViewPassaportes],
    active_org: ActiveOrgOptional,
    p_g: Annotated[str | None, Query()] = None,
    funcao: Annotated[str | None, Query()] = None,
):
    """Lista tripulantes ativos com seus passaportes."""
    can_view_img = await has_org_permission(
        user, session, active_org, IMG_RESOURCE, 'view'
    )
    query = (
        select(
            Tripulante.id.label('trip_id'),
            User.id.label('user_id'),
            User.p_g,
            User.nome_guerra,
            User.nome_completo,
            User.saram,
            User.telefone,
            Passaporte.id.label('passaporte_id'),
            Passaporte.passaporte.label('passaporte_num'),
            Passaporte.data_expedicao_passaporte,
            Passaporte.validade_passaporte,
            Passaporte.visa.label('visa_num'),
            Passaporte.data_expedicao_visa,
            Passaporte.validade_visa,
            Passaporte.passaporte_file_path,
            Passaporte.visa_file_path,
        )
        .select_from(Tripulante)
        .join(User, User.id == Tripulante.user_id)
        .join(PostoGrad, PostoGrad.short == User.p_g)
        .outerjoin(
            Passaporte,
            Passaporte.user_id == User.id,
        )
        .where(
            Tripulante.active.is_(True),
            User.active.is_(True),
        )
        .order_by(
            PostoGrad.ant.asc(),
            User.ult_promo.asc(),
            User.ant_rel.asc(),
            User.id,
        )
    )

    if p_g:
        pgs = [p.strip() for p in p_g.split(',') if p.strip()]
        query = query.where(User.p_g.in_(pgs))

    if funcao:
        funcs = [f.strip() for f in funcao.split(',') if f.strip()]
        query = query.where(
            exists(
                select(Funcao.id).where(
                    Funcao.trip_id == Tripulante.id,
                    Funcao.func.in_(funcs),
                )
            )
        )

    rows = await session.execute(query)
    items = [
        TripPassaporteOut(
            trip_id=r.trip_id,
            user_id=r.user_id,
            p_g=r.p_g,
            nome_guerra=r.nome_guerra,
            nome_completo=r.nome_completo,
            saram=r.saram,
            telefone=r.telefone,
            passaporte=PassaportePublic(
                id=r.passaporte_id,
                user_id=r.user_id,
                passaporte=r.passaporte_num,
                data_expedicao_passaporte=r.data_expedicao_passaporte,
                validade_passaporte=r.validade_passaporte,
                visa=r.visa_num,
                data_expedicao_visa=r.data_expedicao_visa,
                validade_visa=r.validade_visa,
                passaporte_url=_signed_url_opt(r.passaporte_file_path)
                if can_view_img
                else None,
                visa_url=_signed_url_opt(r.visa_file_path)
                if can_view_img
                else None,
            )
            if r.passaporte_id is not None
            else None,
        )
        for r in rows.all()
    ]

    return success_response(data=items)


@router.get(
    '/user/{user_id}',
    response_model=ApiResponse[PassaportePublic | None],
)
async def get_passaporte_by_user(
    user_id: int,
    session: Session,
    user: Annotated[User, Depends(get_current_user)],
    active_org: ActiveOrgOptional,
):
    # Self-service: o próprio militar vê o seu passaporte (portal FatBird),
    # mesmo sem `passaportes.view` (recurso administrativo, que o tripulante
    # não possui). Terceiros exigem a permissão de role na org ativa.
    is_owner = user.id == user_id
    await ensure_org_permission_or_owner(
        user, session, active_org, 'passaportes', 'view', user_id
    )

    passaporte = await session.scalar(
        select(Passaporte).where(Passaporte.user_id == user_id)
    )
    if not passaporte:
        return success_response(data=None)

    # A imagem do próprio documento é sempre visível ao dono; terceiros só
    # com `passaporte.image.view`.
    can_view_img = is_owner or await has_org_permission(
        user, session, active_org, IMG_RESOURCE, 'view'
    )

    return success_response(data=_to_public(passaporte, can_view_img))


@router.put(
    '/{trip_id}',
    response_model=ApiResponse[None],
)
async def upsert_passaporte(
    trip_id: int,
    session: Session,
    dados: PassaporteUpdate,
    active_org: ActiveOrgOptional,
    user: Annotated[User, Depends(get_current_user)],
):
    """Cria ou atualiza passaporte de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    passaporte = await session.scalar(
        select(Passaporte).where(Passaporte.user_id == tripulante.user_id)
    )

    # Granularidade real: editar exige 'update'; cadastrar novo exige
    # 'create'. A ação é decidida pela existência do passaporte.
    action = 'update' if passaporte else 'create'
    if not await has_org_permission(
        user, session, active_org, 'passaportes', action
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail=f'Permissão negada: passaportes.{action}',
        )

    if passaporte:
        for key, value in dados.model_dump(exclude_unset=True).items():
            setattr(passaporte, key, value)
        message = 'Passaporte atualizado com sucesso'
    else:
        passaporte = Passaporte(
            user_id=tripulante.user_id,
            passaporte=dados.passaporte,
            data_expedicao_passaporte=dados.data_expedicao_passaporte,
            validade_passaporte=dados.validade_passaporte,
            visa=dados.visa,
            data_expedicao_visa=dados.data_expedicao_visa,
            validade_visa=dados.validade_visa,
        )
        session.add(passaporte)
        message = 'Passaporte cadastrado com sucesso'

    await session.commit()

    return success_response(message=message)


@router.post(
    '/{trip_id}/imagem/{tipo}',
    response_model=ApiResponse[PassaportePublic],
)
async def upload_imagem_passaporte(
    trip_id: int,
    tipo: TipoImagem,
    file: UploadFile,
    session: Session,
    active_org: ActiveOrgOptional,
    user: Annotated[User, Depends(get_current_user)],
):
    """Faz upload (JPG/PNG normalizado p/ JPEG) da imagem do tipo dado."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    militar = await session.scalar(
        select(User).where(User.id == tripulante.user_id)
    )
    if not militar:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não encontrado',
        )

    passaporte = await session.scalar(
        select(Passaporte).where(Passaporte.user_id == tripulante.user_id)
    )
    key_antiga = (
        (
            passaporte.passaporte_file_path
            if tipo is TipoImagem.passaporte
            else passaporte.visa_file_path
        )
        if passaporte
        else None
    )

    # Granularidade real: substituir imagem existente exige 'update';
    # enviar a primeira imagem do tipo exige 'create'. Checa antes de ler/
    # normalizar o arquivo (evita trabalho pesado p/ quem não tem acesso).
    action = 'update' if key_antiga else 'create'
    if not await has_org_permission(
        user, session, active_org, IMG_RESOURCE, action
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail=f'Permissão negada: {IMG_RESOURCE}.{action}',
        )

    conteudo = await file.read()
    if len(conteudo) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Arquivo excede o limite de 10 MB',
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

    # Cria o registro vazio se ainda não existe (análogo ao upsert): só o
    # vínculo do usuário, demais campos nulos.
    if not passaporte:
        passaporte = Passaporte(
            user_id=tripulante.user_id,
            passaporte=None,
            data_expedicao_passaporte=None,
            validade_passaporte=None,
            visa=None,
            data_expedicao_visa=None,
            validade_visa=None,
        )
        session.add(passaporte)

    now = datetime.now(tz=UTC)
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    nome = _nome_ascii(militar.nome_guerra)
    prefix = (
        PASSAPORTE_PREFIX if tipo is TipoImagem.passaporte else VISA_PREFIX
    )
    path = f'{prefix}/{tripulante.user_id}/{timestamp}_{nome}.jpg'

    upload_file(
        bucket=BUCKET,
        path=path,
        data=conteudo,
        content_type='image/jpeg',
        size=tamanho,
    )

    if tipo is TipoImagem.passaporte:
        passaporte.passaporte_file_path = path
    else:
        passaporte.visa_file_path = path

    # Rollback storage↔banco: se o commit falhar, o objeto recém-enviado
    # fica órfão no bucket — removemos antes de propagar o erro.
    try:
        await session.commit()
    except Exception:
        logger.exception('Erro ao salvar imagem do passaporte no banco')
        delete_file(BUCKET, path)
        raise

    await session.refresh(passaporte)

    # Após persistir a nova key, remove a antiga (tolerando falha, para não
    # quebrar o fluxo se o objeto físico já não existir).
    if key_antiga and key_antiga != path:
        try:
            delete_file(BUCKET, key_antiga)
        except Exception:
            logger.warning(
                'Falha ao remover imagem antiga do passaporte (%s)',
                key_antiga,
                exc_info=True,
            )

    return success_response(
        data=_to_public(passaporte),
        message='Imagem enviada com sucesso',
    )


@router.delete(
    '/{trip_id}/imagem/{tipo}',
    response_model=ApiResponse[PassaportePublic],
)
async def delete_imagem_passaporte(
    trip_id: int,
    tipo: TipoImagem,
    session: Session,
    _: Annotated[User, DeleteImgPassaporte],
):
    """Remove a imagem do tipo dado do bucket e zera a coluna."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    passaporte = await session.scalar(
        select(Passaporte).where(Passaporte.user_id == tripulante.user_id)
    )
    if not passaporte:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Passaporte nao encontrado',
        )

    key = (
        passaporte.passaporte_file_path
        if tipo is TipoImagem.passaporte
        else passaporte.visa_file_path
    )
    if not key:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Imagem não encontrada',
        )

    if tipo is TipoImagem.passaporte:
        passaporte.passaporte_file_path = None
    else:
        passaporte.visa_file_path = None

    await session.commit()
    await session.refresh(passaporte)

    # Pós-commit: remove o objeto do bucket. A coluna já está zerada (sem
    # referência), então uma falha aqui só deixa um órfão — log e segue.
    try:
        delete_file(BUCKET, key)
    except Exception:
        logger.warning(
            'Falha ao remover imagem do passaporte (%s)',
            key,
            exc_info=True,
        )

    return success_response(
        data=_to_public(passaporte),
        message='Imagem removida com sucesso',
    )


@router.get(
    '/imagens/orfas',
    response_model=ApiResponse[ImagensOrfasResumo],
    dependencies=[DeleteImgPassaporte],
)
async def get_imagens_orfas(session: Session):
    """Imagens de passaporte/visto de militares inativos (limpeza)."""
    result = await session.execute(
        select(Passaporte, User)
        .join(User, User.id == Passaporte.user_id)
        .where(
            User.active.is_(False),
            or_(
                Passaporte.passaporte_file_path.is_not(None),
                Passaporte.visa_file_path.is_not(None),
            ),
        )
        .order_by(User.nome_guerra, User.id)
    )

    itens = []
    total_imagens = 0
    for passaporte, militar in result.all():
        tem_p = passaporte.passaporte_file_path is not None
        tem_v = passaporte.visa_file_path is not None
        total_imagens += int(tem_p) + int(tem_v)
        itens.append(
            ImagemOrfaPublic(
                user_id=militar.id,
                p_g=militar.p_g,
                nome_guerra=militar.nome_guerra,
                nome_completo=militar.nome_completo,
                tem_passaporte=tem_p,
                tem_visa=tem_v,
            )
        )

    return success_response(
        data=ImagensOrfasResumo(
            total_imagens=total_imagens,
            total_militares=len(itens),
            itens=itens,
        ),
    )


@router.delete(
    '/imagens/orfas',
    response_model=ApiResponse[ImagensOrfasDeleteResponse],
    dependencies=[DeleteImgPassaporte],
)
async def delete_imagens_orfas(
    payload: ImagensOrfasDelete,
    session: Session,
):
    """Remove as imagens dos militares inativos selecionados."""
    result = await session.execute(
        select(Passaporte)
        .join(User, User.id == Passaporte.user_id)
        .where(
            User.active.is_(False),
            Passaporte.user_id.in_(payload.user_ids),
        )
    )
    passaportes = result.scalars().all()

    # Zera as colunas e coleta as keys; o bucket é limpo após o commit
    # (sem referência pendente — falha vira só um órfão logado).
    keys: list[str] = []
    for passaporte in passaportes:
        if passaporte.passaporte_file_path:
            keys.append(passaporte.passaporte_file_path)
            passaporte.passaporte_file_path = None
        if passaporte.visa_file_path:
            keys.append(passaporte.visa_file_path)
            passaporte.visa_file_path = None

    await session.commit()

    deleted = 0
    for key in keys:
        try:
            delete_file(BUCKET, key)
            deleted += 1
        except Exception:
            logger.warning(
                'Falha ao remover imagem órfã do passaporte (%s)',
                key,
                exc_info=True,
            )

    return success_response(
        data=ImagensOrfasDeleteResponse(deleted=deleted),
        message=f'{deleted} imagem(ns) removida(s)',
    )


@router.delete(
    '/{trip_id}',
    response_model=ApiResponse[None],
)
async def delete_passaporte(
    trip_id: int,
    session: Session,
    _: Annotated[User, DeletePassaportes],
):
    """Remove passaporte de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    passaporte = await session.scalar(
        select(Passaporte).where(Passaporte.user_id == tripulante.user_id)
    )
    if not passaporte:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Passaporte nao encontrado',
        )

    # Keys das imagens do registro, p/ limpar o bucket após remover a linha
    # (evita objetos órfãos no storage).
    keys = [
        k
        for k in (
            passaporte.passaporte_file_path,
            passaporte.visa_file_path,
        )
        if k
    ]

    await session.delete(passaporte)
    await session.commit()

    # Pós-commit: remove os objetos do bucket, tolerando falha (o registro
    # já saiu do banco; um objeto físico ausente não deve quebrar o fluxo).
    for key in keys:
        try:
            delete_file(BUCKET, key)
        except Exception:
            logger.warning(
                'Falha ao remover imagem do passaporte removido (%s)',
                key,
                exc_info=True,
            )

    return success_response(message='Passaporte removido com sucesso')
