import asyncio
import hashlib
import logging
from contextlib import suppress
from datetime import date, datetime
from http import HTTPStatus
from pathlib import PurePosixPath
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.relatorio_voo import RelatorioVoo
from fcontrol_api.models.shared.aeronaves import Aeronave, TenantProjeto
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.estatistica.relatorio_voo import (
    RelatoriosVooPeriodoOut,
    RelatorioVooArquivoOut,
    RelatorioVooOut,
    RelatorioVooUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    get_current_user,
    permission_checker,
)
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.services.pdf import comprimir_pdf, contar_paginas
from fcontrol_api.services.storage import (
    delete_file,
    get_signed_url,
    upload_file,
)
from fcontrol_api.utils.responses import success_response

logger = logging.getLogger(__name__)

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/relatorios-voo', tags=['estatistica'])

# Um bucket por domínio; o nome é constante de código, não configuração.
BUCKET = 'relatorios-voo'
LOG_RESOURCE = 'estatistica.relatorios_voo'
MAX_FILE_SIZE = 10 * 1024 * 1024
# Teto defensivo da listagem: com dezenas por mês não há paginação.
LIMITE_LISTAGEM = 500

# O fuso é explícito de propósito: o container roda em UTC, então
# `date.today()` viraria o dia seguinte às 21h de Brasília e aceitaria como
# "hoje" uma data que ainda é futura para quem está em Brasília.
FUSO_LOCAL = ZoneInfo('America/Sao_Paulo')

ViewRelatorio = Depends(permission_checker(LOG_RESOURCE, 'view'))
CreateRelatorio = Depends(permission_checker(LOG_RESOURCE, 'create'))
UpdateRelatorio = Depends(permission_checker(LOG_RESOURCE, 'update'))
DeleteRelatorio = Depends(permission_checker(LOG_RESOURCE, 'delete'))

STORAGE_INDISPONIVEL = (
    'Armazenamento indisponível; nada foi alterado. Tente novamente.'
)
NAO_ENCONTRADO = 'Relatório não encontrado'


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[RelatorioVooOut],
    dependencies=[CreateRelatorio],
)
async def enviar_relatorio(
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
    file: UploadFile,
    anv: Annotated[str, Form(min_length=4, max_length=4)],
    data: Annotated[date, Form()],
    obs: Annotated[str | None, Form(max_length=500)] = None,
):
    # Copiados já: `session.rollback()` (caminhos de erro abaixo) expira
    # TODOS os objetos da sessão, inclusive `current_user`; ler um atributo
    # dele depois dispararia lazy load síncrono e `MissingGreenlet`.
    autor_id = current_user.id
    autor_p_g = current_user.p_g
    autor_nome = current_user.nome_guerra

    if data > datetime.now(FUSO_LOCAL).date():
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='A data do voo não pode ser futura',
        )
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
    if not conteudo.startswith(b'%PDF-'):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Arquivo não é um PDF válido',
        )

    # Frota da unidade: projetos operados pela org ativa, sem simulador —
    # missão de simulador não gera relatório de voo. Inativa é aceita.
    da_frota = await session.scalar(
        select(Aeronave.matricula).where(
            Aeronave.matricula == anv,
            Aeronave.is_sim.is_(False),
            Aeronave.projeto.in_(
                select(TenantProjeto.projeto).where(
                    TenantProjeto.uae == active_org
                )
            ),
        )
    )
    if da_frota is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f'Aeronave {anv} não pertence à frota da unidade',
        )

    # sha256 do ORIGINAL: a saída do Ghostscript pode variar entre execuções.
    sha256 = hashlib.sha256(conteudo).hexdigest()

    async def rejeitar_se_duplicado():
        # O corpo é a chave de idempotência da fila do digitalizador. Checado
        # antes da compressão (não gasta Ghostscript no caso comum) e de novo
        # a cada tentativa do laço abaixo: uma corrida pode commitar a linha
        # gêmea entre esta checagem e o flush da tentativa anterior.
        existente = await session.scalar(
            select(RelatorioVoo).where(
                RelatorioVoo.uae == active_org, RelatorioVoo.sha256 == sha256
            )
        )
        if existente is not None:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail={
                    'type': 'Arquivo idêntico já enviado',
                    'id': existente.id,
                    'anv': existente.anv,
                    'data': existente.data.isoformat(),
                    'file_path': existente.file_path,
                },
            )

    await rejeitar_se_duplicado()

    comprimido = await asyncio.to_thread(comprimir_pdf, conteudo)
    num_paginas = await asyncio.to_thread(contar_paginas, comprimido)
    obs_limpa = obs.strip() if obs and obs.strip() else None

    relatorio = None
    for tentativa in range(2):
        if tentativa > 0:
            # Rollback já desfez o INSERT desta tentativa; se o motivo da
            # colisão foi o mesmo sha256 (corrida com outro envio do
            # idêntico), a linha concorrente já está commitada e visível
            # agora — devolve o 409 estruturado em vez do genérico de seq.
            await rejeitar_se_duplicado()
        # max+1, nunca count+1: um número apagado no meio não é reaproveitado.
        ultimo = await session.scalar(
            select(func.max(RelatorioVoo.seq)).where(
                RelatorioVoo.uae == active_org,
                RelatorioVoo.anv == anv,
                RelatorioVoo.data == data,
            )
        )
        seq = (ultimo or 0) + 1
        sufixo = '' if seq == 1 else f'_{seq}'
        path = f'{active_org}/{data:%Y}/{anv}_{data.isoformat()}{sufixo}.pdf'
        relatorio = RelatorioVoo(
            uae=active_org,
            anv=anv,
            data=data,
            seq=seq,
            file_path=path,
            file_name=file.filename,
            file_size=len(comprimido),
            sha256=sha256,
            uploaded_by=autor_id,
            num_paginas=num_paginas,
            obs=obs_limpa,
        )
        session.add(relatorio)
        try:
            await session.flush()
            break
        except IntegrityError:
            # Outro envio simultâneo pegou o mesmo seq (ou o mesmo arquivo).
            await session.rollback()
            if tentativa == 1:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail=(
                        'Outro envio para a mesma aeronave e dia ocorreu '
                        'ao mesmo tempo. Tente novamente.'
                    ),
                )

    try:
        await asyncio.to_thread(
            upload_file,
            bucket=BUCKET,
            path=relatorio.file_path,
            data=comprimido,
            content_type='application/pdf',
            size=len(comprimido),
        )
    except (BotoCoreError, ClientError):
        logger.exception('Falha ao enviar %s ao bucket', relatorio.file_path)
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail=STORAGE_INDISPONIVEL,
        )

    await log_user_action(
        session,
        user_id=autor_id,
        action='create',
        resource=LOG_RESOURCE,
        resource_id=relatorio.id,
        after={
            'anv': relatorio.anv,
            'data': relatorio.data.isoformat(),
            'seq': relatorio.seq,
            'file_path': relatorio.file_path,
            'obs': relatorio.obs,
        },
    )
    try:
        await session.commit()
    except SQLAlchemyError:
        # O objeto já está no bucket e a linha não foi gravada: apaga o
        # órfão. Usa `path` local para não depender do estado do objeto ORM
        # depois do rollback.
        with suppress(BotoCoreError, ClientError):
            await asyncio.to_thread(delete_file, BUCKET, path)
        raise
    await session.refresh(relatorio)

    return success_response(
        data=RelatorioVooOut.de(relatorio, autor_p_g, autor_nome)
    )


@router.get(
    '/',
    response_model=ApiResponse[RelatoriosVooPeriodoOut],
    dependencies=[ViewRelatorio],
)
async def listar_relatorios_do_periodo(
    session: Session,
    active_org: ActiveOrg,
    data_ini: Annotated[date, Query()],
    data_fim: Annotated[date, Query()],
    anv: Annotated[str | None, Query(max_length=4)] = None,
):
    if data_ini > data_fim:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='A data inicial não pode ser posterior à data final',
        )
    do_periodo = [
        RelatorioVoo.uae == active_org,
        RelatorioVoo.data >= data_ini,
        RelatorioVoo.data <= data_fim,
    ]

    contagem = await session.execute(
        select(RelatorioVoo.anv, func.count())
        .where(*do_periodo)
        .group_by(RelatorioVoo.anv)
    )

    filtros = list(do_periodo)
    if anv:
        filtros.append(RelatorioVoo.anv == anv)
    linhas = await session.execute(
        select(RelatorioVoo, User.p_g, User.nome_guerra)
        .join(User, User.id == RelatorioVoo.uploaded_by)
        .where(*filtros)
        .order_by(RelatorioVoo.data.desc(), RelatorioVoo.id.desc())
        .limit(LIMITE_LISTAGEM)
    )

    return success_response(
        data=RelatoriosVooPeriodoOut(
            itens=[
                RelatorioVooOut.de(rel, p_g, nome)
                for rel, p_g, nome in linhas.all()
            ],
            contagem_por_anv={a: n for a, n in contagem.all()},
        )
    )


@router.get(
    '/{relatorio_id}/arquivo',
    response_model=ApiResponse[RelatorioVooArquivoOut],
    dependencies=[ViewRelatorio],
)
async def url_do_arquivo(
    relatorio_id: int,
    session: Session,
    active_org: ActiveOrg,
    disposicao: Literal['inline', 'attachment'] = 'inline',
):
    relatorio = await session.scalar(
        select(RelatorioVoo).where(
            RelatorioVoo.id == relatorio_id,
            RelatorioVoo.uae == active_org,
        )
    )
    if relatorio is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail=NAO_ENCONTRADO
        )

    nome = PurePosixPath(relatorio.file_path).name
    url = await asyncio.to_thread(
        get_signed_url,
        BUCKET,
        relatorio.file_path,
        content_disposition=f'{disposicao}; filename="{nome}"',
    )
    return success_response(data=RelatorioVooArquivoOut(url=url))


@router.patch(
    '/{relatorio_id}',
    response_model=ApiResponse[RelatorioVooOut],
    dependencies=[UpdateRelatorio],
)
async def atualizar_observacao(
    relatorio_id: int,
    payload: RelatorioVooUpdate,
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
):
    linha = (
        await session.execute(
            select(RelatorioVoo, User.p_g, User.nome_guerra)
            .join(User, User.id == RelatorioVoo.uploaded_by)
            .where(
                RelatorioVoo.id == relatorio_id,
                RelatorioVoo.uae == active_org,
            )
        )
    ).first()
    if linha is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail=NAO_ENCONTRADO
        )
    relatorio, p_g, nome = linha

    antes = relatorio.obs
    relatorio.obs = payload.obs
    await log_user_action(
        session,
        user_id=current_user.id,
        action='update',
        resource=LOG_RESOURCE,
        resource_id=relatorio.id,
        before={'obs': antes},
        after={'obs': payload.obs},
    )
    await session.commit()
    await session.refresh(relatorio)
    return success_response(data=RelatorioVooOut.de(relatorio, p_g, nome))


@router.delete(
    '/{relatorio_id}',
    response_model=ApiResponse[None],
    dependencies=[DeleteRelatorio],
)
async def excluir_relatorio(
    relatorio_id: int,
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
):
    relatorio = await session.scalar(
        select(RelatorioVoo).where(
            RelatorioVoo.id == relatorio_id,
            RelatorioVoo.uae == active_org,
        )
    )
    if relatorio is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail=NAO_ENCONTRADO
        )

    path = relatorio.file_path
    await log_user_action(
        session,
        user_id=current_user.id,
        action='delete',
        resource=LOG_RESOURCE,
        resource_id=relatorio.id,
        before={
            'anv': relatorio.anv,
            'data': relatorio.data.isoformat(),
            'seq': relatorio.seq,
            'file_path': path,
            'obs': relatorio.obs,
        },
    )
    # Linha primeiro (sem commit), objeto depois, commit por último: se o
    # bucket falhar, o rollback devolve o relatório íntegro.
    await session.delete(relatorio)
    await session.flush()
    try:
        await asyncio.to_thread(delete_file, BUCKET, path)
    except (BotoCoreError, ClientError):
        logger.exception('Falha ao apagar %s do bucket', path)
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail=STORAGE_INDISPONIVEL,
        )
    await session.commit()
    return success_response(message='Relatório excluído')
