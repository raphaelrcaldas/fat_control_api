"""Simulador de custo de missão do FatBird.

Duas rotas servem a mesma tela: `POST /cegep/missoes/simular` (a conta) e
`GET /cegep/missoes/pernoites/cidades` (a busca de cidade, ranqueada por
uso recente da org). Três coisas se trancam aqui:

1. **A postura das rotas.** São as únicas de `/cegep/missoes` sem gate de
   permissão — o tripulante não tem role e `missoes_cegep.view` devolvia
   403, quebrando o simulador. Reintroduzir o gate é uma regressão
   silenciosa (o fetcher do portal engole o erro como "sem dado"), então o
   200 sem role fica travado por teste. O que **não** sai é a identidade:
   sem token continua 401.

2. **A fidelidade do que o front replica.** O FatBird reimplementa a
   projeção de completude a partir de `total_dias` e do `valor_unitario`
   devolvidos aqui, assumindo que são exatamente os campos que o backend
   soma ao vincular uma missão real. Se essa igualdade quebrar, a tela
   passa a exibir dinheiro errado sem nenhum sintoma — o teste de
   fidelidade abaixo é o que segura isso.

3. **O escopo do ranking.** Sem gate de permissão, a única lente da busca
   de cidades é a org ativa do token. Se a contagem vazar de outra
   unidade, o tripulante passa a inferir para onde a vizinha voa.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.routers.cegep.simulador import (
    MAX_DIAS_PERNOITE_SIM,
    MAX_DIAS_SIMULACAO,
    MIN_USOS_DESTAQUE,
)
from fcontrol_api.schemas.cegep.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.services.custos.cache_ref import carregar_caches_custo
from fcontrol_api.services.custos.calculo import calcular_custos_frag_mis
from fcontrol_api.services.custos.leitura import custo_missao
from tests.api.fatbird.conftest import ORG, auth
from tests.factories import FragMisFactory, PernoiteFragFactory

pytestmark = pytest.mark.anyio

ROTA = '/cegep/missoes/simular'
ROTA_CIDADES = '/cegep/missoes/pernoites/cidades'

# Recife (grupo de cidade 2) e um 1º Tenente (grupo de P/G 3) → diária de
# R$ 380,00 na seed. Datas fixas dentro da vigência semeada (2025-01-01+).
CIDADE_RECIFE = 2611606
CIDADE_SP = 3550308
PG = PostoGradEnum.T1
DATA_INI = date(2026, 8, 3)
DATA_FIM = date(2026, 8, 7)

# Org que não é a do tripulante (ele é da `ORG` do conftest).
OUTRA_ORG = '1gt'


def payload_simples(
    *,
    data_ini: date = DATA_INI,
    data_fim: date = DATA_FIM,
    acrec_desloc: bool = False,
    sit: str = 'c',
):
    """Uma perna, um militar — a forma que o FatBird sempre envia."""
    return {
        'acrec_desloc': acrec_desloc,
        'pernoites': [
            {
                'data_ini': data_ini.isoformat(),
                'data_fim': data_fim.isoformat(),
                'cidade_id': CIDADE_RECIFE,
                'meia_diaria': False,
                'acrec_desloc': False,
            }
        ],
        'combinacoes': [{'p_g': PG.value, 'sit': sit, 'qtd': 1}],
    }


# ── Postura da rota ────────────────────────────────────────────────


async def test_tripulante_simula_sem_nenhuma_role(client, trip_token):
    """O POV do FatBird: sem role, sem permissão, e ainda assim 200.

    Este é o teste que impede alguém de recolocar `missoes_cegep.view` na
    rota — é o gate que quebrava o simulador self-service.
    """
    resp = await client.post(
        ROTA, json=payload_simples(), headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['total_dias'] == 4
    assert data['total_geral'] > 0


async def test_simular_sem_token_e_negado(client):
    """Sem gate de permissão, mas não sem identidade."""
    resp = await client.post(ROTA, json=payload_simples())

    assert resp.status_code == HTTPStatus.UNAUTHORIZED


# ── Fidelidade: é o mesmo número que o comissionamento soma ────────


async def test_total_dias_e_valor_batem_com_a_leitura_do_cache(
    client, session, trip_token
):
    """O que a rota devolve == o que `custo_missao` leria da missão real.

    `recalcular_cache_comiss` acumula `missao_data['dias']` e
    `missao_data['valor_total']`, que saem de `custo_missao` lendo o JSONB
    materializado por `calcular_custos_frag_mis`. A projeção do FatBird soma
    `total_dias`/`valor_unitario` desta rota como se fossem esses mesmos
    campos — aqui provamos que são.
    """
    resp = await client.post(
        ROTA, json=payload_simples(), headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']

    # Mesma entrada, pelo caminho da missão persistida: calcular o JSONB e
    # lê-lo com a função que o recálculo do comissionamento usa.
    (
        valores_cache,
        soldos_cache,
        grupos_pg,
        grupos_cidade,
    ) = await carregar_caches_custo(session)
    custos = calcular_custos_frag_mis(
        CustoFragMisInput(acrec_desloc=False),
        [CustoUserFragInput(p_g=PG, sit='c')],
        [
            CustoPernoiteInput(
                id=1,
                data_ini=DATA_INI,
                data_fim=DATA_FIM,
                meia_diaria=False,
                acrec_desloc=False,
                cidade_codigo=CIDADE_RECIFE,
            )
        ],
        grupos_pg,
        grupos_cidade,
        valores_cache,
        soldos_cache,
    )
    mis = custo_missao(PG.value, 'c', {'custos': custos, 'pernoites': []})

    assert data['total_dias'] == mis['dias']
    assert data['total_diarias'] == mis['diarias']
    assert data['combinacoes'][0]['valor_unitario'] == mis['valor_total']


async def test_acrescimo_da_missao_entra_uma_vez_no_valor_unitario(
    client, trip_token
):
    """O acréscimo global soma R$ 95 ao militar, não a cada pernoite.

    O FatBird exibe `acrec_desloc_missao` embaixo do total justamente
    porque ele não aparece em pernoite nenhum do extrato.
    """
    sem = await client.post(
        ROTA, json=payload_simples(), headers=auth(trip_token)
    )
    com = await client.post(
        ROTA,
        json=payload_simples(acrec_desloc=True),
        headers=auth(trip_token),
    )

    assert sem.status_code == com.status_code == HTTPStatus.OK
    d_sem, d_com = sem.json()['data'], com.json()['data']

    assert d_sem['acrec_desloc_missao'] == 0
    assert d_com['acrec_desloc_missao'] > 0
    delta = d_com['total_geral'] - d_sem['total_geral']
    assert delta == pytest.approx(d_com['acrec_desloc_missao'])


# ── Tetos de período (a rota é aberta: sem eles, DoS trivial) ──────


async def test_pernoite_longo_demais_e_recusado(client, trip_token):
    """Um pernoite acima do teto para antes de entrar no cálculo."""
    data_fim = DATA_INI + timedelta(days=MAX_DIAS_PERNOITE_SIM)

    resp = await client.post(
        ROTA,
        json=payload_simples(data_fim=data_fim),
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert 'período maior que' in resp.json()['message']


async def test_pernoite_no_limite_passa(client, trip_token):
    """O teto é inclusivo — exatamente `MAX_DIAS_PERNOITE_SIM` dias vale."""
    data_fim = DATA_INI + timedelta(days=MAX_DIAS_PERNOITE_SIM - 1)

    resp = await client.post(
        ROTA,
        json=payload_simples(data_fim=data_fim),
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK


async def test_soma_dos_pernoites_acima_do_teto_e_recusada(client, trip_token):
    """Cada perna cabe no limite individual, mas o total não.

    Pernoites encadeados (o fim de um é o início do outro) não se
    sobrepõem — a checagem de conflito é estrita —, então este payload só
    pode ser barrado pelo teto agregado.
    """
    dias_por_perna = 210
    p1_fim = DATA_INI + timedelta(days=dias_por_perna - 1)
    p2_fim = p1_fim + timedelta(days=dias_por_perna - 1)
    assert dias_por_perna <= MAX_DIAS_PERNOITE_SIM
    assert dias_por_perna * 2 > MAX_DIAS_SIMULACAO

    resp = await client.post(
        ROTA,
        json={
            'acrec_desloc': False,
            'pernoites': [
                {
                    'data_ini': DATA_INI.isoformat(),
                    'data_fim': p1_fim.isoformat(),
                    'cidade_id': CIDADE_RECIFE,
                    'meia_diaria': False,
                    'acrec_desloc': False,
                },
                {
                    'data_ini': p1_fim.isoformat(),
                    'data_fim': p2_fim.isoformat(),
                    'cidade_id': CIDADE_RECIFE,
                    'meia_diaria': False,
                    'acrec_desloc': False,
                },
            ],
            'combinacoes': [{'p_g': PG.value, 'sit': 'c', 'qtd': 1}],
        },
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert 'no total' in resp.json()['message']


async def test_data_invertida_acusa_a_data_e_nada_mais(client, trip_token):
    """Fim antes do início acusa a data, e só ela.

    O laço que mede o período acumula a duração e checa a ordem das datas
    ao mesmo tempo; este teste trava que juntar as duas coisas não fez o
    payload invertido ganhar uma queixa de "total" que não existe.
    """
    resp = await client.post(
        ROTA,
        json=payload_simples(data_ini=DATA_FIM, data_fim=DATA_INI),
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    message = resp.json()['message']
    assert 'data de fim anterior à de início' in message
    assert 'no total' not in message


# ── Busca de cidade ranqueada (a mesma tela) ───────────────────────


async def semear_pernoites(session, *, uae, cidade_id, qtd):
    """`qtd` pernoites de uma org numa cidade, dentro da janela padrão.

    Um dia distinto por pernoite: datas iguais na mesma missão seriam
    sobreposição, e o ranking conta pernoite, não missão.
    """
    missao = FragMisFactory(uae=uae)
    session.add(missao)
    await session.flush()

    for i in range(qtd):
        dia = date.today() - timedelta(days=i)
        session.add(
            PernoiteFragFactory(
                frag_id=missao.id,
                cidade_id=cidade_id,
                data_ini=dia,
                data_fim=dia,
            )
        )
    await session.commit()


def achar(data, codigo):
    return next((c for c in data if c['codigo'] == codigo), None)


async def test_tripulante_busca_cidade_sem_nenhuma_role(client, trip_token):
    """O gate saiu daqui pelo mesmo motivo que saiu de `/simular`."""
    resp = await client.get(
        ROTA_CIDADES, params={'search': 'recife'}, headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert achar(resp.json()['data'], CIDADE_RECIFE) is not None


async def test_busca_de_cidade_sem_token_e_negada(client):
    resp = await client.get(ROTA_CIDADES, params={'search': 'recife'})

    assert resp.status_code == HTTPStatus.UNAUTHORIZED


async def test_ranking_conta_so_pernoites_da_org_ativa(
    client, session, trip_token
):
    """Uso da org vizinha não aparece — nem como contagem.

    Sem gate de permissão, `ActiveOrg` é a única lente da rota. Se ela
    falhar, o tripulante infere para onde a outra unidade vem voando.
    """
    usos = MIN_USOS_DESTAQUE + 1
    await semear_pernoites(session, uae=ORG, cidade_id=CIDADE_RECIFE, qtd=usos)
    await semear_pernoites(
        session, uae=OUTRA_ORG, cidade_id=CIDADE_SP, qtd=usos
    )

    da_org = await client.get(
        ROTA_CIDADES, params={'search': 'recife'}, headers=auth(trip_token)
    )
    da_outra = await client.get(
        ROTA_CIDADES, params={'search': 'sao paulo'}, headers=auth(trip_token)
    )
    assert da_org.status_code == da_outra.status_code == HTTPStatus.OK

    recife = achar(da_org.json()['data'], CIDADE_RECIFE)
    assert recife['usos'] == usos
    assert recife['mais_usada'] is True

    # A cidade da outra org continua sendo uma opção de busca — o que ela
    # não pode trazer é o uso de lá.
    sp = achar(da_outra.json()['data'], CIDADE_SP)
    assert sp['usos'] == 0
    assert sp['mais_usada'] is False
