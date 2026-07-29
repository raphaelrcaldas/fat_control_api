"""Leitura do cache de custos para o frontend.

`custo_missao` lê o JSONB materializado por `calculo.calcular_custos_frag_mis`
e monta a estrutura consumida pelas telas. Não recalcula nada: quando a
chave pg+sit pedida não existe (cache desatualizado), retorna zerado,
registra em log e sinaliza `custo_inconsistente` — em vez de produzir
dinheiro errado silenciosamente. A chave canônica é a mesma da escrita
(`integridade.chave_pg_sit`), garantindo que ambas concordem.
"""

import logging

from fcontrol_api.services.custos.integridade import chave_pg_sit

logger = logging.getLogger(__name__)


def custo_totais(
    p_g: str,
    sit: str,
    custos_jsonb: dict | None,
    *,
    tem_pernoites: bool,
    missao_id=None,
    n_doc=None,
) -> dict:
    """Totais de uma missão para um pg+sit, direto do JSONB.

    Parte pura de `custo_missao` — não depende de `pernoites`, `users`
    nem de mais nada da missão além do próprio cache. Existe separada
    porque quem só precisa dos agregados (o cache do comissionamento) não
    tem por que carregar e serializar a missão inteira para descartá-la
    em seguida.

    `qtd_ac` aqui conta só o acréscimo da missão; o dos pernoites é somado
    por `custo_missao`, que é quem os tem em mãos.
    """
    chave = chave_pg_sit(p_g, sit)
    zerado = {'dias': 0, 'diarias': 0, 'valor_total': 0, 'qtd_ac': 0}

    # Cache vazio. É esperado em missão sem custo, mas suspeito quando há
    # pernoites (indica recálculo pendente) — nesse caso, sinaliza.
    if not custos_jsonb or not isinstance(custos_jsonb, dict):
        if tem_pernoites:
            logger.warning(
                'Custos ausentes na missão id=%s n_doc=%s: cache vazio '
                'com pernoites presentes (recálculo pendente). '
                'Valores retornados como zero.',
                missao_id,
                n_doc,
            )
            return {**zerado, 'custo_inconsistente': True}
        return {**zerado, 'custo_inconsistente': False}

    acrec_desloc = custos_jsonb.get('acrec_desloc_missao', 0)
    totais_pg_sit = custos_jsonb.get('totais_pg_sit', {})

    inconsistente = chave not in totais_pg_sit
    if inconsistente:
        logger.warning(
            'Custo inconsistente na missão id=%s n_doc=%s: combinação %s '
            'ausente no cache (disponíveis: %s). '
            'valor_total retornado como zero.',
            missao_id,
            n_doc,
            chave,
            list(totais_pg_sit.keys()),
        )

    return {
        'dias': custos_jsonb.get('total_dias', 0),
        'diarias': custos_jsonb.get('total_diarias', 0),
        'valor_total': totais_pg_sit.get(chave, {}).get('total_valor', 0),
        'qtd_ac': 1 if acrec_desloc > 0 else 0,
        'custo_inconsistente': inconsistente,
    }


def custo_missao(p_g: str, sit: str, mis: dict) -> dict:
    """
    Lê custos do JSONB pré-calculado e monta estrutura para o frontend.

    O campo `custos` é um cache materializado na escrita. Quando a chave
    pg+sit pedida não está presente (cache desatualizado em relação aos
    militares/pernoites da missão), os valores retornam zerados — mas o
    fato é registrado em log e sinalizado via `custo_inconsistente`, em
    vez de produzir dinheiro errado silenciosamente.
    """
    chave = chave_pg_sit(p_g, sit)
    custos_jsonb = mis.get('custos', {})

    totais = custo_totais(
        p_g,
        sit,
        custos_jsonb,
        tem_pernoites=bool(mis.get('pernoites')),
        missao_id=mis.get('id'),
        n_doc=mis.get('n_doc'),
    )
    if totais.pop('custo_inconsistente'):
        mis['custo_inconsistente'] = True
    mis.update(totais)

    if not custos_jsonb or not isinstance(custos_jsonb, dict):
        return mis

    # Popular custos de cada pernoite
    for pnt in mis.get('pernoites', []):
        pernoite_key = f'pernoite_{pnt["id"]}'
        pernoite_custos = custos_jsonb.get(pernoite_key, {})

        # Grupo da cidade
        pnt['gp_cid'] = pernoite_custos.get('grupo_cid', 3)

        # Custos específicos para este pg+sit
        pg_sit_custos = pernoite_custos.get(chave, {})

        # Montar estrutura de custo compatível
        pnt['custo'] = {
            'subtotal': pg_sit_custos.get('subtotal', 0),
            'ac_desloc': pernoite_custos.get('ac_desloc', 0),
            'vals': pg_sit_custos.get('vals', []),
            'dias': pernoite_custos.get('dias', 0),
        }

        # Contar acréscimos de deslocamento
        if pernoite_custos.get('ac_desloc', 0) > 0:
            mis['qtd_ac'] += 1

    return mis
