"""Integridade do cache de custos: chave canônica + hash dos inputs.

Este módulo é a fonte única da **chave** `pg_<valor>_sit_<valor>` e do
**hash** dos inputs locais. Cálculo (escrita), leitura e verificação
derivam ambos daqui — assim escrita e leitura nunca divergem na forma da
chave (a causa do bug histórico em que o enum era serializado como
`PostoGradEnum.S3` em vez de `3s`).
"""

import hashlib
import json
from enum import Enum

from fcontrol_api.schemas.cegep.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)


def chave_pg_sit(p_g, sit: str) -> str:
    """Monta a chave canônica pg+sit do cache de custos.

    Aceita `p_g` como str ou PostoGradEnum: na mesma sessão de escrita o
    objeto ORM pode ainda conter o enum (antes do refresh), e `f'{enum}'`
    produziria 'PostoGradEnum.S3' em vez de '3s'. Normaliza sempre para o
    valor, garantindo que escrita e leitura gerem exatamente a mesma chave.
    """
    pg = p_g.value if isinstance(p_g, Enum) else p_g
    return f'pg_{pg}_sit_{sit}'


def gerar_hash_custos(
    frag_mis: CustoFragMisInput,
    users_frag: list[CustoUserFragInput],
    pernoites: list[CustoPernoiteInput],
) -> str:
    """Hash canônico (sha256) dos inputs locais que determinam o cache de
    custos de uma missão.

    Permite detectar drift entre o cache materializado em `custos` e os
    dados atuais da missão. Os militares entram como conjunto único de
    (p_g, sit): o cache é construído por combinação única, então militares
    repetidos não alteram a integridade. Recebe os mesmos schemas validados
    usados por `calcular_custos_frag_mis`, garantindo que escrita e
    verificação derivem o hash da mesma representação canônica.
    """
    payload = {
        'acrec_desloc': bool(frag_mis.acrec_desloc),
        'users': sorted({f'{uf.p_g.value}|{uf.sit}' for uf in users_frag}),
        'pernoites': sorted(
            '|'.join((
                str(p.id),
                p.data_ini.isoformat(),
                p.data_fim.isoformat(),
                str(int(p.meia_diaria)),
                str(int(p.acrec_desloc)),
                str(p.cidade_codigo),
            ))
            for p in pernoites
        ),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def verificar_integridade_custos(
    frag_mis: CustoFragMisInput,
    users_frag: list[CustoUserFragInput],
    pernoites: list[CustoPernoiteInput],
    custos_jsonb: dict | None,
) -> bool:
    """Verifica se o cache de custos está íntegro frente aos inputs locais
    atuais da missão (fase 1: apenas dados da própria missão).

    - Sem cache: íntegro só se a missão não tem pernoites (sem custo).
    - Cache legado sem `_input_hash`: tratado como íntegro (sem base de
      comparação; a heurística de chave faltante em `custo_missao` ainda
      cobre o pior caso).
    - Caso geral: recomputa o hash dos inputs e compara.
    """
    if not custos_jsonb or not isinstance(custos_jsonb, dict):
        return not pernoites
    hash_armazenado = custos_jsonb.get('_input_hash')
    if not hash_armazenado:
        return True
    hash_atual = gerar_hash_custos(frag_mis, users_frag, pernoites)
    return hash_atual == hash_armazenado
