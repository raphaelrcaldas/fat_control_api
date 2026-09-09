"""Servicos de quadrinhos (quads)."""

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.enums.notificacao import NotifAudiencia, NotifTipo
from fcontrol_api.models.shared.quads import QuadsGroup, QuadsType
from fcontrol_api.services.notificacoes import notificar_usuarios


async def rotulos_de_tipos(
    session: AsyncSession, type_ids: Iterable[int], active_org: str
) -> dict[int, tuple[str, str]]:
    """Mapeia id do tipo -> (nome do tipo, nome do grupo), numa consulta.

    O join em `quads_group` amarra o tipo a org ativa: sem essa amarra um
    gestor gravaria quadrinho de tipo de outra unidade e o rotulo dela
    viajaria dentro do payload da notificacao entregue ao tripulante.

    Um id ausente do retorno e um tipo que nao pertence a org (ou nao
    existe) — quem chama decide se isso e 404.
    """
    linhas = await session.execute(
        select(QuadsType.id, QuadsType.long, QuadsGroup.long)
        .join(QuadsGroup, QuadsType.group_id == QuadsGroup.id)
        .where(
            QuadsType.id.in_(set(type_ids)),
            QuadsGroup.uae == active_org,
        )
    )
    return {tid: (nome, grupo) for tid, nome, grupo in linhas.all()}


async def notificar_quadro(
    session: AsyncSession,
    *,
    alvo_user_id: int,
    active_org: str,
    tipo: NotifTipo,
    titulo: str,
    type_id: int,
    nome_tipo: str,
    nome_grupo: str,
    func: str,
    qtd: int,
    created_by: int,
) -> None:
    """Avisa o tripulante que ganhou ou perdeu quadrinhos.

    Lancamento e remocao mandam o MESMO payload, mudando so o tipo da
    notificacao e o titulo — por isso o contrato mora aqui, num lugar so.

    `tipo` (id + nome + grupo) e `func` alimentam o deep-link do FatBird
    (/ops/quads?tipo=&func=) e o rotulo do item no sino. A ROTA e o TEXTO
    sao montados pelo front: aqui vai o dado CRU (nome como esta no
    catalogo, minusculo), porque caixa alta e decisao de exibicao — a
    tela de quadrinhos exibe o mesmo rotulo em maiusculas por classe CSS,
    nao por dado.

    Recebe apenas dados ja em memoria (payload validado + linhas das
    queries de validacao): nenhum atributo lazy de ORM, para nao disparar
    select assincrono fora do greenlet.

    `notificar_usuarios` pula o alvo == created_by: quem lancou o proprio
    quadrinho nao recebe "voce recebeu".
    """
    await notificar_usuarios(
        session,
        user_ids=[alvo_user_id],
        uae=active_org,
        audiencia=NotifAudiencia.TRIPULANTE.value,
        tipo=tipo.value,
        titulo=titulo,
        recurso='ops.quadro',
        payload={
            'quantidade': qtd,
            'tipo': {
                'id': type_id,
                'nome': nome_tipo,
                'grupo': nome_grupo,
            },
            'func': func,
        },
        created_by=created_by,
    )
