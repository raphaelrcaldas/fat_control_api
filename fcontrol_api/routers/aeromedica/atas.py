import asyncio
import logging
import unicodedata
from datetime import UTC, date, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.aeromedica.atas import AtaInspecao
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.aeromedica.atas import (
    AtaExtrairResponse,
    AtaInspecaoPublic,
    AtaInspecaoWithUrl,
    AtaUpdate,
    AtaUploadResponse,
    DadosExtraidos,
)
from fcontrol_api.schemas.response import (
    ApiResponse,
    ResponseStatus,
)
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.services.aeromedica_extracao import (
    extrair_dados_ata_bytes,
)
from fcontrol_api.services.pdf import comprimir_pdf
from fcontrol_api.services.storage import (
    delete_file,
    get_signed_url,
    upload_file,
)
from fcontrol_api.utils.responses import success_response

logger = logging.getLogger(__name__)

Session = Annotated[AsyncSession, Depends(get_session)]

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Bucket do domínio aeromédica. O nome do bucket é constante de código
# (não é env/secret) — cada domínio tem o seu. Ver services/storage.py.
BUCKET = 'aeromedica'

# Sub-pasta (prefixo de key) das atas dentro do bucket do domínio, isolando-as
# de outros arquivos da aeromédica (ex.: futuros cartões). Sem acento por
# consistência com as demais keys (o nome do arquivo já é ASCII no upload).
ATAS_PREFIX = 'atas-inspecao'


async def _validar_pdf(file: UploadFile) -> bytes:
    """Valida e retorna conteudo de um PDF."""
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Apenas arquivos PDF são permitidos',
        )

    conteudo = await file.read()

    if len(conteudo) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Arquivo excede o limite de 10 MB',
        )

    if not conteudo[:5].startswith(b'%PDF-'):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Arquivo não é um PDF válido',
        )

    return conteudo


async def _buscar_usuario(
    session: AsyncSession, user_id: int, active_org: str
) -> User:
    """Busca usuario da org ativa ou levanta 404 (escopo por unidade)."""
    user = await session.scalar(
        select(User).where(User.id == user_id, User.unidade == active_org)
    )
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não encontrado',
        )
    return user


async def _verificar_duplicata(
    session: AsyncSession,
    user_id: int,
    letra: str | None,
    realizacao: date | None,
    validade: date | None,
    exclude_id: int | None = None,
) -> None:
    """Levanta 409 se ata duplicada existir.

    `exclude_id` ignora a própria ata na checagem (usado no update, para
    não conflitar consigo mesma).
    """
    filtros = [AtaInspecao.user_id == user_id]

    if letra:
        filtros.append(AtaInspecao.letra_finalidade == letra)
    else:
        filtros.append(AtaInspecao.letra_finalidade.is_(None))
    if realizacao:
        filtros.append(AtaInspecao.data_realizacao == realizacao)
    else:
        filtros.append(AtaInspecao.data_realizacao.is_(None))
    if validade:
        filtros.append(AtaInspecao.validade_inspsau == validade)
    else:
        filtros.append(AtaInspecao.validade_inspsau.is_(None))
    if exclude_id is not None:
        filtros.append(AtaInspecao.id != exclude_id)

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


async def _upsert_cemal(
    session: AsyncSession,
    user_id: int,
    validade: date | None,
) -> bool:
    """Atualiza o CEMAL do cartão apenas se a validade for mais recente.

    Retorna True se o CEMAL foi criado ou atualizado. Impede que uma ata
    retroativa faça o CEMAL regredir: só uma validade maior que a atual (ou
    o primeiro cartão) atualiza o campo — coerente com "a ata mais recente é
    que vale" exibido no frontend.
    """
    if validade is None:
        return False

    cartao = await session.scalar(
        select(CartaoSaude).where(CartaoSaude.user_id == user_id)
    )
    if cartao is None:
        session.add(
            CartaoSaude(
                user_id=user_id,
                cemal=validade,
                tovn=None,
                imae=None,
            )
        )
        return True

    if cartao.cemal is None or validade > cartao.cemal:
        cartao.cemal = validade
        return True

    return False


router = APIRouter(prefix='/atas', tags=['Atas de Inspeção'])

# Atas seguem o mesmo recurso RBAC dos cartões de saúde (dado sensível de
# saúde). Leitura exige 'view'; anexar/extrair é 'create'; remover é 'delete'.
ViewCartao = Depends(permission_checker('aeromedica.cartoes', 'view'))
CreateCartao = Depends(permission_checker('aeromedica.cartoes', 'create'))
UpdateCartao = Depends(permission_checker('aeromedica.cartoes', 'update'))
DeleteCartao = Depends(permission_checker('aeromedica.cartoes', 'delete'))


@router.post(
    '/extrair',
    response_model=ApiResponse[AtaExtrairResponse],
    dependencies=[CreateCartao],
)
async def extrair_ata(
    session: Session,
    active_org: ActiveOrg,
    user_id: int,
    file: UploadFile,
):
    """Extrai dados de um PDF de ata sem salvar."""
    conteudo = await _validar_pdf(file)
    user = await _buscar_usuario(session, user_id, active_org)
    dados = await asyncio.to_thread(extrair_dados_ata_bytes, conteudo)

    extracao_vazia = not any((
        dados['letra_finalidade'],
        dados['data_realizacao'],
        dados['validade_inspsau'],
    ))

    dados_extraidos = DadosExtraidos(
        nome_completo=dados['nome_completo'],
        letra_finalidade=dados['letra_finalidade'],
        data_realizacao=dados['data_realizacao'],
        validade_inspsau=dados['validade_inspsau'],
    )

    response_data = AtaExtrairResponse(
        dados_extraidos=dados_extraidos,
        extracao_vazia=extracao_vazia,
    )

    # Verificar divergencia de nome (aviso, nao erro)
    nome_pdf = dados.get('nome_completo')
    if not extracao_vazia and nome_pdf:
        nome_db = user.nome_completo.strip().upper()
        nome_pdf_up = nome_pdf.strip().upper()
        if nome_pdf_up != nome_db:
            return ApiResponse(
                status=ResponseStatus.WARNING,
                data=response_data,
                message='nome_divergente',
                errors={
                    'nome_ata': nome_pdf_up,
                    'nome_sistema': nome_db,
                },
            )

    return success_response(data=response_data)


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[AtaUploadResponse],
    dependencies=[CreateCartao],
)
async def upload_ata(
    session: Session,
    active_org: ActiveOrg,
    user_id: int,
    file: UploadFile,
    dados_confirmados: bool = False,
    conf_letra: Annotated[str | None, Query(max_length=1)] = None,
    conf_realizacao: date | None = None,
    conf_validade: date | None = None,
):
    """Upload de PDF de ata de inspecao de saude."""
    conteudo = await _validar_pdf(file)
    user = await _buscar_usuario(session, user_id, active_org)

    if dados_confirmados:
        dados = {
            'nome_completo': None,
            'letra_finalidade': conf_letra,
            'data_realizacao': conf_realizacao,
            'validade_inspsau': conf_validade,
        }
        extracao_vazia = not any((
            conf_letra,
            conf_realizacao,
            conf_validade,
        ))
    else:
        dados = await asyncio.to_thread(extrair_dados_ata_bytes, conteudo)
        extracao_vazia = not any((
            dados['letra_finalidade'],
            dados['data_realizacao'],
            dados['validade_inspsau'],
        ))

    # Verificar duplicata (sempre, independente do fluxo)
    if not extracao_vazia:
        await _verificar_duplicata(
            session,
            user_id,
            dados['letra_finalidade'],
            dados['data_realizacao'],
            dados['validade_inspsau'],
        )

    # Montar nome do arquivo: NOME_GUERRA_YYYY-MM-DD.pdf
    nome_guerra = user.nome_guerra.strip().replace(' ', '_').lower()
    nome_guerra = ''.join(
        c
        for c in unicodedata.normalize('NFD', nome_guerra)
        if unicodedata.category(c) != 'Mn'
    )
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
    path = f'{ATAS_PREFIX}/{user_id}/{timestamp}_{file_name}'

    await asyncio.to_thread(
        upload_file,
        bucket=BUCKET,
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

        # Atualiza o cemal do cartão apenas se esta validade for a mais
        # recente (não regride com ata retroativa). Ver _upsert_cemal.
        cemal_atualizado = await _upsert_cemal(
            session, user_id, dados['validade_inspsau']
        )

        await session.commit()
        await session.refresh(ata)
    except Exception:
        logger.exception('Erro ao salvar ata no banco')
        await asyncio.to_thread(delete_file, BUCKET, path)
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
    dependencies=[ViewCartao],
)
async def get_atas_by_user(
    user_id: int,
    session: Session,
    active_org: ActiveOrg,
):
    """Lista atas de inspecao de um usuario."""
    result = await session.execute(
        select(AtaInspecao)
        .join(User, AtaInspecao.user_id == User.id)
        .where(
            AtaInspecao.user_id == user_id,
            User.unidade == active_org,
        )
        .order_by(
            AtaInspecao.created_at.desc(),
            AtaInspecao.id.desc(),
        )
    )
    atas = result.scalars().all()

    # get_signed_url é síncrono (boto3): gera todas as URLs em paralelo em
    # threads para não bloquear o event loop uma a uma.
    urls = await asyncio.gather(
        *(
            asyncio.to_thread(get_signed_url, BUCKET, ata.file_path)
            for ata in atas
        )
    )

    data = []
    for ata, url in zip(atas, urls, strict=True):
        ata_dict = AtaInspecaoPublic.model_validate(ata).model_dump()
        ata_dict['url'] = url
        data.append(AtaInspecaoWithUrl(**ata_dict))

    return success_response(data=data)


@router.patch(
    '/{ata_id}',
    response_model=ApiResponse[AtaInspecaoPublic],
    dependencies=[UpdateCartao],
)
async def update_ata(
    ata_id: int,
    body: AtaUpdate,
    session: Session,
    active_org: ActiveOrg,
):
    """Atualiza dados de uma ata (preenchimento manual)."""
    ata = await session.scalar(
        select(AtaInspecao)
        .join(User, AtaInspecao.user_id == User.id)
        .where(AtaInspecao.id == ata_id, User.unidade == active_org)
    )
    if not ata:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ata não encontrada',
        )

    # Impede que a edição transforme esta ata numa cópia de outra do mesmo
    # militar (mesma checagem do upload, ignorando a própria ata).
    if any((
        body.letra_finalidade,
        body.data_realizacao,
        body.validade_inspsau,
    )):
        await _verificar_duplicata(
            session,
            ata.user_id,
            body.letra_finalidade,
            body.data_realizacao,
            body.validade_inspsau,
            exclude_id=ata.id,
        )

    ata.letra_finalidade = body.letra_finalidade
    ata.data_realizacao = body.data_realizacao
    ata.validade_inspsau = body.validade_inspsau

    # Atualiza o cemal apenas se esta validade for a mais recente.
    await _upsert_cemal(session, ata.user_id, body.validade_inspsau)

    await session.commit()
    await session.refresh(ata)

    return success_response(
        data=AtaInspecaoPublic.model_validate(ata),
        message='Ata atualizada com sucesso',
    )


@router.delete(
    '/{ata_id}',
    response_model=ApiResponse[None],
    dependencies=[DeleteCartao],
)
async def delete_ata(
    ata_id: int,
    session: Session,
    active_org: ActiveOrg,
):
    """Remove ata do bucket e do banco."""
    ata = await session.scalar(
        select(AtaInspecao)
        .join(User, AtaInspecao.user_id == User.id)
        .where(AtaInspecao.id == ata_id, User.unidade == active_org)
    )

    if not ata:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ata não encontrada',
        )

    file_path = ata.file_path

    # Remove primeiro do banco (fonte da verdade) e só então do storage,
    # tolerando falha física — evita apagar o arquivo e o commit falhar
    # depois, deixando registro órfão apontando para objeto inexistente.
    await session.delete(ata)
    await session.commit()

    try:
        await asyncio.to_thread(delete_file, BUCKET, file_path)
    except Exception:
        logger.warning(
            'Falha ao remover arquivo da ata %s (%s) do storage',
            ata_id,
            file_path,
            exc_info=True,
        )

    return success_response(
        message='Ata removida com sucesso',
    )
