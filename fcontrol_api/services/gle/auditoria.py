"""Snapshots de GLE para auditoria, sem consultas ou escrita no banco."""

from fcontrol_api.models.cegep.gle import MissaoGle
from fcontrol_api.models.shared.estados_cidades import GrupoLocEsp


def snapshot_localidade(loc: GrupoLocEsp) -> dict:
    return {
        'cidade_id': loc.cidade_id,
        'grupo': loc.grupo,
        'fuso': loc.fuso,
        'icaos': sorted(item.icao for item in loc.icaos),
    }


def snapshot_missao(missao: MissaoGle) -> dict:
    """Estado JSON-serializável da missão para auditoria.

    Lê somente escalares e coleções que já estejam em memória. O chamador
    precisa garantir que `trechos` e `militares` foram carregados para não
    disparar lazy-load fora do contexto greenlet.
    """
    trechos = [
        {
            'loc_esp_id': trecho.loc_esp_id,
            'chegada': trecho.chegada.isoformat(),
            'afastamento': trecho.afastamento.isoformat(),
        }
        for trecho in sorted(
            missao.trechos,
            key=lambda item: (
                item.loc_esp_id,
                item.chegada,
                item.afastamento,
            ),
        )
    ]
    militares = [
        {'user_id': militar.user_id, 'p_g': militar.p_g}
        for militar in sorted(
            missao.militares,
            key=lambda item: (item.user_id, item.p_g),
        )
    ]
    return {
        'descricao': missao.descricao,
        'obs': missao.obs,
        'trechos': trechos,
        'militares': militares,
    }
