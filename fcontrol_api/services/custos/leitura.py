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

    # Cache vazio. É esperado em missão sem custo, mas suspeito quando há
    # pernoites (indica recálculo pendente) — nesse caso, sinaliza.
    if not custos_jsonb or not isinstance(custos_jsonb, dict):
        if mis.get('pernoites'):
            logger.warning(
                'Custos ausentes na missão id=%s n_doc=%s: cache vazio '
                'com pernoites presentes (recálculo pendente). '
                'Valores retornados como zero.',
                mis.get('id'),
                mis.get('n_doc'),
            )
            mis['custo_inconsistente'] = True
        mis['dias'] = 0
        mis['diarias'] = 0
        mis['valor_total'] = 0
        mis['qtd_ac'] = 0
        return mis

    # Extrair totais gerais
    mis['dias'] = custos_jsonb.get('total_dias', 0)
    mis['diarias'] = custos_jsonb.get('total_diarias', 0)
    acrec_desloc = custos_jsonb.get('acrec_desloc_missao', 0)
    mis['qtd_ac'] = 1 if acrec_desloc > 0 else 0

    # Extrair total de valor para este pg+sit
    totais_pg_sit = custos_jsonb.get('totais_pg_sit', {})
    if chave not in totais_pg_sit:
        logger.warning(
            'Custo inconsistente na missão id=%s n_doc=%s: combinação %s '
            'ausente no cache (disponíveis: %s). '
            'valor_total retornado como zero.',
            mis.get('id'),
            mis.get('n_doc'),
            chave,
            list(totais_pg_sit.keys()),
        )
        mis['custo_inconsistente'] = True
    total_valor = totais_pg_sit.get(chave, {}).get('total_valor', 0)
    mis['valor_total'] = total_valor

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
