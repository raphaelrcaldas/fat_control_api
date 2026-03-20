import asyncio
import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.aeromedica.atas import AtaInspecao
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.aeromedica.atas import (
    AllBucketsStatsPublic,
    AtaInspecaoPublic,
    AtaInspecaoWithUrl,
    AtaOrfaPublic,
    AtasOrfasResumo,
    AtaUpdate,
    AtaUploadResponse,
    BucketStatsPublic,
    DadosExtraidos,
    StorageStatsPublic,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.services.aeromedica_extracao import (
    extrair_dados_ata_bytes,
)
from fcontrol_api.services.pdf import comprimir_pdf
from fcontrol_api.services.storage import (
    delete_file,
    get_all_buckets_stats,
    get_bucket_stats,
    get_signed_url,
    upload_file,
)
from fcontrol_api.utils.responses import success_response

logger = logging.getLogger(__name__)

Session = Annotated[AsyncSession, Depends(get_session)]

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

router = APIRouter(prefix='/atas', tags=['Atas de Inspeção'])


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[AtaUploadResponse],
)
async def upload_ata(
    session: Session,
    user_id: int,
    file: UploadFile,
    ignorar_nome: bool = False,
):
    """Upload de PDF de ata de inspeção de saúde."""
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Apenas arquivos PDF são permitidos',
        )

    conteudo = await file.read()
    tamanho = len(conteudo)

    if tamanho > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Arquivo excede o limite de 10 MB',
        )

    # Validar magic bytes do PDF
    if not conteudo[:5].startswith(b'%PDF-'):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Arquivo não é um PDF válido',
        )

    # Buscar nome_guerra do usuario
    user = await session.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não encontrado',
        )

    # Extrair dados do PDF
    dados = extrair_dados_ata_bytes(conteudo)

    extracao_vazia = not any((
        dados['letra_finalidade'],
        dados['data_realizacao'],
        dados['validade_inspsau'],
    ))

    # Validações só quando houve extração
    if not extracao_vazia:
        # Verificar nome do PDF vs banco
        nome_pdf = dados.get('nome_completo')
        if nome_pdf and not ignorar_nome:
            nome_db = user.nome_completo.strip().upper()
            nome_pdf_upper = nome_pdf.strip().upper()
            if nome_pdf_upper != nome_db:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail={
                        'type': 'nome_divergente',
                        'nome_ata': nome_pdf_upper,
                        'nome_sistema': nome_db,
                    },
                )

        # Verificar duplicata (mesma letra + datas)
        filtros = [AtaInspecao.user_id == user_id]
        if dados['letra_finalidade']:
            filtros.append(
                AtaInspecao.letra_finalidade == dados['letra_finalidade']
            )
        else:
            filtros.append(AtaInspecao.letra_finalidade.is_(None))
        if dados['data_realizacao']:
            filtros.append(
                AtaInspecao.data_realizacao == dados['data_realizacao']
            )
        else:
            filtros.append(AtaInspecao.data_realizacao.is_(None))
        if dados['validade_inspsau']:
            filtros.append(
                AtaInspecao.validade_inspsau == dados['validade_inspsau']
            )
        else:
            filtros.append(AtaInspecao.validade_inspsau.is_(None))

        duplicata = await session.scalar(
            select(AtaInspecao.id).where(and_(*filtros))
        )
        if duplicata:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail='Já existe uma ata com a mesma'
                ' letra, data de realização e'
                ' validade para este militar',
            )

    # Montar nome do arquivo: NOME_GUERRA_YYYY-MM-DD.pdf
    nome_guerra = user.nome_guerra.strip().replace(' ', '_').lower()
    now = datetime.now(tz=UTC)
    if dados['data_realizacao']:
        data_str = dados['data_realizacao'].strftime('%Y-%m-%d')
    else:
        data_str = now.strftime('%Y-%m-%d')
    file_name = f'{nome_guerra}_{data_str}.pdf'

    # Comprimir PDF
    conteudo = await asyncio.to_thread(comprimir_pdf, conteudo)
    tamanho = len(conteudo)

    # Upload para o bucket
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    path = f'{user_id}/{timestamp}_{file_name}'

    upload_file(
        path=path,
        data=conteudo,
        content_type='application/pdf',
        size=tamanho,
    )

    # Salvar no banco
    try:
        ata = AtaInspecao(
            user_id=user_id,
            file_path=path,
            file_name=file_name,
            file_size=tamanho,
            letra_finalidade=dados['letra_finalidade'],
            data_realizacao=dados['data_realizacao'],
            validade_inspsau=dados['validade_inspsau'],
        )

        session.add(ata)

        # Atualizar cemal do CartaoSaude se validade extraída
        cemal_atualizado = False
        if dados['validade_inspsau']:
            cartao = await session.scalar(
                select(CartaoSaude).where(CartaoSaude.user_id == user_id)
            )
            if not cartao:
                cartao = CartaoSaude(
                    user_id=user_id,
                    cemal=dados['validade_inspsau'],
                    ag_cemal=None,
                    tovn=None,
                    imae=None,
                )
                session.add(cartao)
            else:
                cartao.cemal = dados['validade_inspsau']
            cemal_atualizado = True

        await session.commit()
        await session.refresh(ata)
    except Exception:
        logger.exception('Erro ao salvar ata no banco')
        delete_file(path)
        raise

    dados_extraidos = DadosExtraidos(
        nome_completo=dados['nome_completo'],
        letra_finalidade=dados['letra_finalidade'],
        data_realizacao=dados['data_realizacao'],
        validade_inspsau=dados['validade_inspsau'],
    )

    response = AtaUploadResponse(
        ata=AtaInspecaoPublic.model_validate(ata),
        dados_extraidos=dados_extraidos,
        cemal_atualizado=cemal_atualizado,
        extracao_vazia=extracao_vazia,
    )

    msg = (
        'Ata enviada. Preencha os dados manualmente.'
        if extracao_vazia
        else 'Ata enviada com sucesso'
    )
    return success_response(data=response, message=msg)


@router.get(
    '/user/{user_id}',
    response_model=ApiResponse[list[AtaInspecaoWithUrl]],
)
async def get_atas_by_user(
    user_id: int,
    session: Session,
):
    """Lista atas de inspeção de um usuário."""
    result = await session.execute(
        select(AtaInspecao)
        .where(AtaInspecao.user_id == user_id)
        .order_by(
            AtaInspecao.created_at.desc(),
            AtaInspecao.id.desc(),
        )
    )
    atas = result.scalars().all()

    data = []
    for ata in atas:
        url = get_signed_url(ata.file_path)
        ata_dict = AtaInspecaoPublic.model_validate(ata).model_dump()
        ata_dict['url'] = url
        data.append(AtaInspecaoWithUrl(**ata_dict))

    return success_response(data=data)


@router.patch(
    '/{ata_id}',
    response_model=ApiResponse[AtaInspecaoPublic],
)
async def update_ata(
    ata_id: int,
    body: AtaUpdate,
    session: Session,
):
    """Atualiza dados de uma ata (preenchimento manual)."""
    ata = await session.scalar(
        select(AtaInspecao).where(AtaInspecao.id == ata_id)
    )
    if not ata:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ata não encontrada',
        )

    ata.letra_finalidade = body.letra_finalidade
    ata.data_realizacao = body.data_realizacao
    ata.validade_inspsau = body.validade_inspsau

    # Atualizar cemal se validade informada
    if body.validade_inspsau:
        cartao = await session.scalar(
            select(CartaoSaude).where(CartaoSaude.user_id == ata.user_id)
        )
        if not cartao:
            cartao = CartaoSaude(
                user_id=ata.user_id,
                cemal=body.validade_inspsau,
                ag_cemal=None,
                tovn=None,
                imae=None,
            )
            session.add(cartao)
        else:
            cartao.cemal = body.validade_inspsau

    await session.commit()
    await session.refresh(ata)

    return success_response(
        data=AtaInspecaoPublic.model_validate(ata),
        message='Ata atualizada com sucesso',
    )


@router.delete(
    '/{ata_id}',
    response_model=ApiResponse[None],
)
async def delete_ata(
    ata_id: int,
    session: Session,
):
    """Remove ata do bucket e do banco."""
    ata = await session.scalar(
        select(AtaInspecao).where(AtaInspecao.id == ata_id)
    )

    if not ata:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ata não encontrada',
        )

    delete_file(ata.file_path)
    await session.delete(ata)
    await session.commit()

    return success_response(message='Ata removida com sucesso')


@router.get(
    '/orfas',
    response_model=ApiResponse[AtasOrfasResumo],
)
async def get_atas_orfas(session: Session):
    """Lista atas de usuários inativos."""
    result = await session.execute(
        select(AtaInspecao, User.nome_guerra, User.nome_completo)
        .join(User, AtaInspecao.user_id == User.id)
        .where(User.active.is_(False))
        .order_by(User.nome_guerra, AtaInspecao.id)
    )
    rows = result.all()

    atas = []
    total_size = 0
    for ata, nome_guerra, nome_completo in rows:
        total_size += ata.file_size
        atas.append(AtaOrfaPublic(
            id=ata.id,
            user_id=ata.user_id,
            nome_guerra=nome_guerra,
            nome_completo=nome_completo,
            file_name=ata.file_name,
            file_size=ata.file_size,
            created_at=ata.created_at,
        ))

    return success_response(
        data=AtasOrfasResumo(
            total_atas=len(atas),
            total_size=total_size,
            atas=atas,
        ),
    )


@router.delete(
    '/orfas',
    response_model=ApiResponse[None],
)
async def delete_atas_orfas(session: Session):
    """Remove todas as atas de usuários inativos."""
    result = await session.execute(
        select(AtaInspecao)
        .join(User, AtaInspecao.user_id == User.id)
        .where(User.active.is_(False))
    )
    atas = result.scalars().all()

    for ata in atas:
        delete_file(ata.file_path)
        await session.delete(ata)

    await session.commit()

    return success_response(
        message=f'{len(atas)} ata(s) órfã(s) removida(s)',
    )


@router.get(
    '/storage/stats',
    response_model=ApiResponse[StorageStatsPublic],
)
async def storage_stats():
    """Retorna estatísticas de uso do bucket."""
    stats = await asyncio.to_thread(get_bucket_stats)
    return success_response(
        data=StorageStatsPublic(**stats),
    )


@router.get(
    '/storage/all',
    response_model=ApiResponse[AllBucketsStatsPublic],
)
async def all_buckets_stats():
    """Retorna estatísticas de todos os buckets."""
    stats = await asyncio.to_thread(get_all_buckets_stats)
    buckets = [BucketStatsPublic(**b) for b in stats['buckets']]
    return success_response(
        data=AllBucketsStatsPublic(
            total_size=stats['total_size'],
            total_objects=stats['total_objects'],
            buckets=buckets,
        ),
    )
