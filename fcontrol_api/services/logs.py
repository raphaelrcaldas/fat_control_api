import json
from datetime import datetime, timezone

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

    `obs` (da missão e de cada pernoite) só entra quando preenchida — em
    branco vira ruído no log.

    ATENÇÃO (lazy-load/greenlet): esta função só lê atributos já em
    memória — nunca dispara select. `m` precisa ter os escalares (n_doc,
    tipo_doc, indenizavel, acrec_desloc, afast, regres, desc, obs, tipo);
    `militares` precisa ter, por item, `.user_id`/`.user.nome_guerra`/
    `.p_g`/`.sit` já carregados; `pernoites` precisa ter `.cidade.nome`/
    `.cidade.uf`/`.data_ini`/`.data_fim`/`.acrec_desloc`/`.meia_diaria`/
    `.obs`;
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
                'nome': u.user.nome_guerra.upper(),
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
                'cidade': f'{p.cidade.nome}-{p.cidade.uf}',
                'data_ini': p.data_ini.isoformat(),
                'data_fim': p.data_fim.isoformat(),
                'acrec_desloc': p.acrec_desloc,
                'meia_diaria': p.meia_diaria,
                **({'obs': p.obs} if p.obs else {}),
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
        **({'obs': m.obs} if m.obs else {}),
        'tipo': m.tipo,
        'militares': militares_out,
        'pernoites': pernoites_out,
        'etiquetas': etiquetas_out,
    }


def _iso_utc(dt: datetime) -> str:
    """Serializa um datetime em ISO-8601 sempre normalizado para UTC.

    As colunas de etapa (`dt_dep`/`dt_arr`) são `DateTime(timezone=True)`:
    o banco devolve *aware* em UTC, mas o mesmo instante pode chegar
    *naive* pelo payload validado. Sem normalizar, `before` e `after`
    serializariam o mesmo instante de formas diferentes e **todo** update
    pareceria ter mudado. Naive é assumido como UTC — é o que o asyncpg
    faz ao gravar em `timestamptz`.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def ordem_snapshot(
    o,
    etapas,
    tripulacao,
    etiquetas,
) -> dict:
    """Snapshot JSON-serializável rico de uma OM para auditoria.

    Além dos escalares da ordem, inclui campos especiais/etapas/
    tripulação/etiquetas — sem isso, edições de rota, tripulante ou
    rótulo ficam invisíveis no before/after.

    `doc_ref` só entra quando preenchido — em branco vira ruído no log.
    `tvoo_etp` é sempre **calculado** aqui (dt_arr - dt_dep em minutos),
    nunca lido do atributo: o payload (`EtapaCreate`) não tem esse campo
    e o model tem, e calcular nos dois lados é o que garante simetria do
    diff.

    ATENÇÃO (lazy-load/greenlet): esta função só lê atributos já em
    memória — nunca dispara select. `o` precisa ter os escalares (numero,
    tipo, matricula_anv, projeto, status, esf_aer, data_saida, doc_ref) e
    `campos_especiais`; `etapas` precisa ter, por item, `.dt_dep`/
    `.dt_arr`/`.origem`/`.dest`/`.alternativa`/`.tvoo_alt`/`.qtd_comb`/
    `.esf_aer`; `tripulacao` precisa ter `.funcao`/`.tripulante_id`/
    `.p_g`/`.tripulante.user.nome_guerra`; `etiquetas` precisa ter
    `.nome`. Por duck-typing servem tanto as instâncias ORM (OrdemEtapa,
    OrdemTripulacao com `.tripulante`/`.user` eager por lazy='selectin',
    Etiqueta) quanto os itens já validados do payload (EtapaCreate) e as
    linhas devolvidas por `criar_tripulacao_batch` — escolha a fonte que
    já está garantidamente carregada no ponto de chamada, para não
    disparar lazy-load assíncrono fora do greenlet. Em especial, as
    coleções do próprio `ordem` ficam **stale** após criar etapas/
    tripulação novas (elas nunca são anexadas à coleção): nesse caso use
    o payload / o retorno do batch.
    """
    campos_out = sorted(
        (
            campo if isinstance(campo, dict) else campo.model_dump()
            for campo in (o.campos_especiais or [])
        ),
        key=lambda item: (item['label'], item['valor']),
    )
    etapas_out = sorted(
        (
            {
                'dt_dep': _iso_utc(e.dt_dep),
                'dt_arr': _iso_utc(e.dt_arr),
                'origem': e.origem,
                'dest': e.dest,
                'alternativa': e.alternativa,
                'tvoo_etp': int((e.dt_arr - e.dt_dep).total_seconds() / 60),
                'tvoo_alt': e.tvoo_alt,
                'qtd_comb': e.qtd_comb,
                'esf_aer': e.esf_aer,
            }
            for e in etapas
        ),
        key=lambda item: (item['dt_dep'], item['origem'], item['dest']),
    )
    tripulacao_out = sorted(
        (
            {
                'funcao': t.funcao,
                'tripulante_id': t.tripulante_id,
                'p_g': t.p_g,
                'nome': t.tripulante.user.nome_guerra.upper(),
            }
            for t in tripulacao
        ),
        key=lambda item: (item['funcao'], item['tripulante_id']),
    )
    etiquetas_out = sorted(e.nome for e in etiquetas)

    return {
        'numero': o.numero,
        'tipo': o.tipo,
        'matricula_anv': o.matricula_anv,
        'projeto': o.projeto,
        'status': o.status,
        'esf_aer': o.esf_aer,
        'data_saida': (o.data_saida.isoformat() if o.data_saida else None),
        **({'doc_ref': o.doc_ref} if o.doc_ref else {}),
        'campos_especiais': campos_out,
        'etapas': etapas_out,
        'tripulacao': tripulacao_out,
        'etiquetas': etiquetas_out,
    }
