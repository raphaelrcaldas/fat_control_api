import json

from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.security.logs import UserActionLog


async def log_user_action(
    session: AsyncSession,
    user_id: int,
    action: str,
    resource: str,
    resource_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
):
    log = UserActionLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        before=json.dumps(before) if before is not None else None,
        after=json.dumps(after) if after is not None else None,
    )
    session.add(log)


def missao_snapshot(
    m,
    militares,
    pernoites,
    etiquetas,
) -> dict:
    """Snapshot JSON-serializável rico de uma missão para auditoria.

    Além dos escalares da missão, inclui militares/pernoites/etiquetas —
    sem isso, edições de tripulação, pernoite ou rótulo ficam invisíveis
    no before/after.

    ATENÇÃO (lazy-load/greenlet): esta função só lê atributos já em
    memória — nunca dispara select. `m` precisa ter os escalares (n_doc,
    tipo_doc, indenizavel, acrec_desloc, afast, regres, desc, obs, tipo);
    `militares` precisa ter, por item, `.user_id`/`.user.nome_guerra`/
    `.p_g`/`.sit` já carregados; `pernoites` precisa ter `.cidade.nome`/
    `.data_ini`/`.data_fim`/`.acrec_desloc`/`.meia_diaria`/`.obs`;
    `etiquetas` precisa ter `.nome`. Por duck-typing, tanto instâncias ORM
    (UserFrag/PernoiteFrag/Etiqueta, com `.user`/`.cidade` já eager
    carregados via lazy='selectin') quanto os itens já validados do
    payload (UserFragMis/PernoiteFragMis/EtiquetaSchema) servem aqui —
    escolha a fonte que já está garantidamente carregada no ponto de
    chamada, para não disparar lazy-load assíncrono fora do greenlet.
    """
    militares_out = sorted(
        (
            {
                'user_id': u.user_id,
                'nome': u.user.nome_guerra,
                'p_g': u.p_g,
                'sit': u.sit,
            }
            for u in militares
        ),
        key=lambda item: item['user_id'],
    )
    pernoites_out = sorted(
        (
            {
                'cidade': p.cidade.nome,
                'data_ini': p.data_ini.isoformat(),
                'data_fim': p.data_fim.isoformat(),
                'acrec_desloc': p.acrec_desloc,
                'meia_diaria': p.meia_diaria,
                'obs': p.obs,
            }
            for p in pernoites
        ),
        key=lambda item: (item['data_ini'], item['cidade']),
    )
    etiquetas_out = sorted(e.nome for e in etiquetas)

    return {
        'n_doc': m.n_doc,
        'tipo_doc': m.tipo_doc,
        'indenizavel': m.indenizavel,
        'acrec_desloc': m.acrec_desloc,
        'afast': m.afast.isoformat() if m.afast else None,
        'regres': m.regres.isoformat() if m.regres else None,
        'desc': m.desc,
        'obs': m.obs,
        'tipo': m.tipo,
        'militares': militares_out,
        'pernoites': pernoites_out,
        'etiquetas': etiquetas_out,
    }
