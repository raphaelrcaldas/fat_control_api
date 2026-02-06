"""
Factories para criação de objetos de teste usando factory_boy.
"""

import datetime
import typing

import factory
import factory.fuzzy

from fcontrol_api.enums.indisp import IndispEnum
from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.models.cegep.dados_bancarios import DadosBancarios
from fcontrol_api.models.cegep.diarias import DiariaValor, GrupoCidade, GrupoPg
from fcontrol_api.models.cegep.missoes import (
    Etiqueta,
    FragMis,
    PernoiteFrag,
    UserFrag,
)
from fcontrol_api.models.nav.aerodromos import Aerodromo
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.indisp import Indisp
from fcontrol_api.models.public.om import OrdemEtapa, OrdemMissao
from fcontrol_api.models.public.posto_grad import Soldo
from fcontrol_api.models.public.quads import Quad
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.auth import OAuth2Client
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.schemas.funcoes import funcs, opers, proj
from fcontrol_api.schemas.tripulantes import uaes
from fcontrol_api.utils.validators import calcular_dv_saram


def gerar_cpf_valido(n: int) -> str:
    """
    Gera um CPF válido com dígitos verificadores corretos.

    Args:
        n: Número sequencial para gerar o CPF base

    Returns:
        CPF válido (11 dígitos) com DVs corretos
    """
    # Gera os 9 primeiros dígitos
    base = str(n).zfill(9)

    # Calcula primeiro DV
    soma = sum(int(base[i]) * (10 - i) for i in range(9))
    resto = soma % 11
    dv1 = 0 if resto < 2 else 11 - resto

    # Calcula segundo DV
    base_com_dv1 = base + str(dv1)
    soma = sum(int(base_com_dv1[i]) * (11 - i) for i in range(10))
    resto = soma % 11
    dv2 = 0 if resto < 2 else 11 - resto

    return base + str(dv1) + str(dv2)


def gerar_saram_valido(n: int) -> str:
    """
    Gera um SARAM válido com dígito verificador correto.

    Args:
        n: Número sequencial para gerar o SARAM base

    Returns:
        SARAM válido (7 dígitos) com DV correto como string
    """
    # Gera um número base de 6 dígitos
    numero_base = str(100000 + n)
    # Calcula o DV
    dv = calcular_dv_saram(numero_base)
    # Retorna o SARAM completo como string
    return numero_base + str(dv)


class UserFactory(factory.Factory):
    """
    Factory para criar usuários de teste.
    """

    class Meta:
        model = User

    p_g = factory.fuzzy.FuzzyChoice(['2s', '3s', 'cb'])
    esp = factory.fuzzy.FuzzyText(length=3)
    nome_guerra = factory.Sequence(lambda n: f'fulano{n}')
    nome_completo = factory.Sequence(lambda n: f'fulano{n} da silva')
    id_fab = factory.Sequence(lambda n: str(100000 + n))
    saram = factory.Sequence(gerar_saram_valido)
    unidade = factory.fuzzy.FuzzyText(length=5)
    cpf = factory.Sequence(gerar_cpf_valido)
    email_fab = factory.LazyAttribute(
        lambda obj: f'{obj.nome_guerra}@fab.mil.br'
    )
    email_pess = factory.LazyAttribute(
        lambda obj: f'{obj.nome_guerra}@email.mil.br'
    )
    ant_rel = factory.fuzzy.FuzzyInteger(1, 999)
    nasc = factory.fuzzy.FuzzyDate(datetime.date(1970, 1, 1))
    ult_promo = factory.fuzzy.FuzzyDate(datetime.date(2010, 1, 1))
    password = factory.LazyAttribute(lambda obj: f'{obj.nome_guerra}-secret')


class TripFactory(factory.Factory):
    """
    Factory para criar tripulantes.
    """

    class Meta:
        model = Tripulante

    user_id: int
    trig = factory.Sequence(
        lambda n: (
            f'{chr(97 + n % 26)}{chr(97 + (n // 26) % 26)}'
            f'{chr(97 + (n // 676) % 26)}'
        )
    )
    active = True  # Padrão ativo (mais comum em testes)
    uae = factory.fuzzy.FuzzyChoice(typing.get_args(uaes))


class FuncFactory(factory.Factory):
    """
    Factory para criar funções vinculadas a tripulantes.
    """

    class Meta:
        model = Funcao

    trip_id: int
    func = factory.fuzzy.FuzzyChoice(typing.get_args(funcs))
    oper = factory.fuzzy.FuzzyChoice(typing.get_args(opers))
    proj = factory.fuzzy.FuzzyChoice(typing.get_args(proj))
    data_op = None


class QuadFactory(factory.Factory):
    """
    Factory para criar quadrantes vinculados a tripulantes.

    ATENÇÃO: Esta factory requer seed data para quads_type.
    O type_id hardcoded (1) assume que existe um quads_type.id = 1
    no banco de dados.

    IMPORTANTE: Requer trip_id ao criar.

    Status: ⚠️ DESABILITADA até seed data de quads_type ser criada.

    Uso (quando habilitada):
        quad = QuadFactory(trip_id=trip.id)
        quad_especifico = QuadFactory(
            trip_id=trip.id,
            type_id=2,
            description='Descrição customizada'
        )

    TODO: Criar seed data para quads_type ou usar SubFactory
    """

    class Meta:
        model = Quad

    description = factory.fuzzy.FuzzyText(length=6)
    type_id = 1  # ⚠️ HARDCODED - requer quads_type.id = 1 no seed
    value = factory.fuzzy.FuzzyDate(datetime.date(2024, 1, 1))
    trip_id: int


class OAuth2ClientFactory(factory.Factory):
    """
    Factory para criar clientes OAuth2.
    """

    class Meta:
        model = OAuth2Client

    client_id = factory.Sequence(lambda n: f'test-client-{n}')
    client_secret = factory.fuzzy.FuzzyText(length=32)
    redirect_uri = 'http://localhost:3000/callback'
    is_confidential = False


class IndispFactory(factory.Factory):
    """
    Factory para criar indisponibilidades de teste.

    IMPORTANTE: Requer user_id e created_by ao criar.

    Uso:
        indisp = IndispFactory(user_id=user.id, created_by=creator.id)
        indisp_ferias = IndispFactory(
            user_id=user.id,
            created_by=creator.id,
            mtv='fer',
            obs='Ferias programadas'
        )
    """

    class Meta:
        model = Indisp

    user_id: int
    created_by: int
    date_start = factory.LazyFunction(datetime.date.today)
    date_end = factory.LazyAttribute(
        lambda _: datetime.date.today() + datetime.timedelta(days=7)
    )
    mtv = factory.fuzzy.FuzzyChoice([e.value for e in IndispEnum])
    obs = factory.Sequence(lambda n: f'Observacao teste {n}')


class OrdemMissaoFactory(factory.Factory):
    """
    Factory para criar Ordens de Missão de teste.

    IMPORTANTE: Requer created_by ao criar.

    Uso:
        ordem = OrdemMissaoFactory(created_by=user.id)
        ordem_rascunho = OrdemMissaoFactory(
            created_by=user.id,
            status='rascunho'
        )
    """

    class Meta:
        model = OrdemMissao

    numero = factory.Sequence(lambda n: f'OM-{n:04d}/2025')
    matricula_anv = factory.fuzzy.FuzzyInteger(2800, 2899)
    tipo = factory.fuzzy.FuzzyChoice([
        'instrucao',
        'operacional',
        'transporte',
    ])
    created_by: int
    projeto = factory.fuzzy.FuzzyChoice(['KC-390'])
    status = 'aprovada'
    campos_especiais = []
    uae = factory.fuzzy.FuzzyChoice(['1/1 GT', '2/1 GT', '3/1 GT'])
    esf_aer = factory.fuzzy.FuzzyInteger(0, 5)


class OrdemEtapaFactory(factory.Factory):
    """
    Factory para criar Etapas de Ordem de Missão de teste.

    IMPORTANTE: Requer ordem_id ao criar.

    Uso:
        etapa = OrdemEtapaFactory(ordem_id=ordem.id)
        etapa_especifica = OrdemEtapaFactory(
            ordem_id=ordem.id,
            origem='SBGL',
            dest='SBBR',
            alternativa='SBCF'
        )
    """

    class Meta:
        model = OrdemEtapa

    ordem_id: int
    dt_dep = factory.LazyFunction(
        lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    origem = factory.fuzzy.FuzzyChoice(['SBGL', 'SBGR', 'SBRF', 'SBCF'])
    dest = factory.fuzzy.FuzzyChoice(['SBBR', 'SBSP', 'SBJD', 'SBSV'])
    dt_arr = factory.LazyAttribute(
        lambda obj: obj.dt_dep + datetime.timedelta(hours=1)
    )
    alternativa = factory.fuzzy.FuzzyChoice(['SBCF', 'SBSP', 'SBGL', 'SBBR'])
    tvoo_etp = 60  # 1 hora em minutos
    tvoo_alt = 30  # 30 minutos
    qtd_comb = factory.fuzzy.FuzzyInteger(10, 20)
    esf_aer = factory.fuzzy.FuzzyText(length=10)


class DadosBancariosFactory(factory.Factory):
    """
    Factory para criar dados bancários de teste.

    IMPORTANTE: Requer user_id ao criar.

    Uso:
        dados = DadosBancariosFactory(user_id=user.id)
        dados_customizado = DadosBancariosFactory(
            user_id=user.id,
            banco='Banco do Brasil',
            codigo_banco='001',
            agencia='1234-5',
            conta='12345-6'
        )
    """

    class Meta:
        model = DadosBancarios

    user_id: int
    banco = factory.Sequence(lambda n: f'Banco Teste {n}')
    codigo_banco = factory.Sequence(lambda n: str(100 + n).zfill(3))
    agencia = factory.Sequence(lambda n: f'{n:04d}-{n % 10}')
    conta = factory.Sequence(lambda n: f'{n:05d}-{n % 10}')


class UserActionLogFactory(factory.Factory):
    """
    Factory para criar logs de acoes de usuario.

    IMPORTANTE: Requer user_id ao criar.

    Uso:
        log = UserActionLogFactory(user_id=user.id)
        log_customizado = UserActionLogFactory(
            user_id=user.id,
            action='create',
            resource='users',
            resource_id=123
        )
    """

    class Meta:
        model = UserActionLog

    user_id: int
    action = factory.fuzzy.FuzzyChoice(['create', 'update', 'delete', 'read'])
    resource = factory.fuzzy.FuzzyChoice(['users', 'trips', 'quads', 'indisp'])
    resource_id = factory.Sequence(lambda n: n + 1)
    before = None
    after = None


class SoldoFactory(factory.Factory):
    """
    Factory para criar soldos de teste.

    IMPORTANTE: Requer pg (posto/graduacao) valido do seed data.
    Valores disponiveis: 'cb', '2s', '3s', '1t', 'cp', 'mj', etc.

    Uso:
        soldo = SoldoFactory(pg='cb')
        soldo_customizado = SoldoFactory(
            pg='2s',
            valor=5000.00,
            data_inicio=date(2025, 1, 1)
        )
    """

    class Meta:
        model = Soldo

    pg = 'cb'  # Cabo - disponivel no seed data
    data_inicio = factory.LazyFunction(datetime.date.today)
    data_fim = None
    valor = factory.fuzzy.FuzzyFloat(3000.0, 15000.0)


class GrupoCidadeFactory(factory.Factory):
    """
    Factory para criar grupos de cidade de teste.

    IMPORTANTE: Requer cidade_id valido (codigo da cidade no seed).
    Codigos disponiveis: 3550308 (SP), 3304557 (RJ), 5300108 (BSB), etc.

    Uso:
        grupo = GrupoCidadeFactory(grupo=1, cidade_id=3550308)
    """

    class Meta:
        model = GrupoCidade

    grupo: int
    cidade_id: int


class GrupoPgFactory(factory.Factory):
    """
    Factory para criar grupos de posto/graduacao de teste.

    IMPORTANTE: Requer pg_short valido do seed data.
    Valores disponiveis: 'cb', '2s', '3s', '1t', 'cp', 'mj', etc.

    Uso:
        grupo = GrupoPgFactory(grupo=1, pg_short='cb')
    """

    class Meta:
        model = GrupoPg

    grupo: int
    pg_short: str


class DiariaValorFactory(factory.Factory):
    """
    Factory para criar valores de diarias de teste.

    Uso:
        valor = DiariaValorFactory(grupo_pg=1, grupo_cid=1)
        valor_customizado = DiariaValorFactory(
            grupo_pg=2,
            grupo_cid=1,
            valor=350.00,
            data_inicio=date(2025, 1, 1)
        )
    """

    class Meta:
        model = DiariaValor

    grupo_pg: int
    grupo_cid: int
    valor = factory.fuzzy.FuzzyFloat(100.0, 500.0)
    data_inicio = factory.LazyFunction(datetime.date.today)
    data_fim = None


class AerodromoFactory(factory.Factory):
    """
    Factory para criar aerodromos de teste.

    Uso:
        aerodromo = AerodromoFactory()
        aerodromo_customizado = AerodromoFactory(
            nome='Aeroporto de Guarulhos',
            codigo_icao='SBGR',
            codigo_iata='GRU'
        )
    """

    class Meta:
        model = Aerodromo

    nome = factory.Sequence(lambda n: f'Aeroporto Teste {n}')
    codigo_icao = factory.Sequence(lambda n: f'SB{n:02d}')
    codigo_iata = None
    latitude = factory.fuzzy.FuzzyFloat(-33.0, 5.0)
    longitude = factory.fuzzy.FuzzyFloat(-73.0, -35.0)
    elevacao = factory.fuzzy.FuzzyFloat(0.0, 1500.0)
    pais = 'BR'
    utc = -3
    base_aerea = None
    codigo_cidade = None
    cidade_manual = None


class ComissFactory(factory.Factory):
    """
    Factory para criar comissionamentos de teste.

    IMPORTANTE: Requer user_id ao criar.

    Uso:
        comiss = ComissFactory(user_id=user.id)
        comiss_fechado = ComissFactory(
            user_id=user.id,
            status='fechado'
        )
    """

    class Meta:
        model = Comissionamento

    user_id: int
    status = 'aberto'
    dep = False

    data_ab = factory.LazyFunction(datetime.date.today)
    qtd_aj_ab = 30.0
    valor_aj_ab = 5000.00

    data_fc = factory.LazyAttribute(
        lambda obj: obj.data_ab + datetime.timedelta(days=90)
    )
    qtd_aj_fc = 30.0
    valor_aj_fc = 5000.00

    dias_cumprir = 60

    doc_prop = factory.Sequence(lambda n: f'PROP-{n:04d}/2025')
    doc_aut = factory.Sequence(lambda n: f'AUT-{n:04d}/2025')
    doc_enc = None


class FragMisFactory(factory.Factory):
    """
    Factory para criar missoes (FragMis) de teste.

    Uso:
        missao = FragMisFactory()
        missao_custom = FragMisFactory(
            desc='Missao de transporte',
            tipo='transporte'
        )
    """

    class Meta:
        model = FragMis

    tipo_doc = factory.fuzzy.FuzzyChoice(['om', 'os'])
    n_doc = factory.Sequence(lambda n: 1000 + n)
    desc = factory.Sequence(lambda n: f'Missao de teste {n}')
    tipo = factory.fuzzy.FuzzyChoice(['adm', 'tal', 'opr'])
    afast = factory.LazyFunction(datetime.datetime.now)
    regres = factory.LazyAttribute(
        lambda obj: obj.afast + datetime.timedelta(days=3)
    )
    acrec_desloc = factory.fuzzy.FuzzyChoice([True, False])
    obs = 'detail teste'
    indenizavel = factory.fuzzy.FuzzyChoice([True, False])


class UserFragFactory(factory.Factory):
    """
    Factory para criar relacao usuario-missao (UserFrag) de teste.

    IMPORTANTE: Requer frag_id e user_id ao criar.

    Situacoes (sit):
        - 'c': Comissionado
        - 'd': Diaria
        - 'g': Grat Rep (Gratificacao por Representacao)

    Uso:
        # Comissionado (padrao)
        user_frag = UserFragFactory(frag_id=missao.id, user_id=user.id)
        user_frag_comiss = UserFragFactory(
            frag_id=missao.id,
            user_id=user.id,
            sit='c',
            p_g='cb'
        )

        # Diaria
        user_frag_diaria = UserFragFactory(
            frag_id=missao.id,
            user_id=user.id,
            sit='d',
            p_g='2s'
        )

        # Gratificacao por Representacao
        user_frag_grat = UserFragFactory(
            frag_id=missao.id,
            user_id=user.id,
            sit='g',
            p_g='1t'
        )
    """

    class Meta:
        model = UserFrag

    frag_id: int
    user_id: int
    sit = 'c'  # comissionado (padrao)
    p_g = 'cb'  # posto/graduacao


class PernoiteFragFactory(factory.Factory):
    """
    Factory para criar pernoites de missao (PernoiteFrag) de teste.

    IMPORTANTE: Requer frag_id e cidade_id ao criar.
    O cidade_id deve ser codigo valido (ex: 3550308 para SP).

    Uso:
        pernoite = PernoiteFragFactory(
            frag_id=missao.id,
            cidade_id=3550308
        )
        pernoite_meia = PernoiteFragFactory(
            frag_id=missao.id,
            cidade_id=3550308,
            meia_diaria=True
        )
    """

    class Meta:
        model = PernoiteFrag

    frag_id: int
    cidade_id = 3550308  # SP do seed
    acrec_desloc = False
    data_ini = factory.LazyFunction(datetime.date.today)
    data_fim = factory.LazyAttribute(
        lambda obj: obj.data_ini + datetime.timedelta(days=3)
    )
    meia_diaria = False
    obs = ''


class EtiquetaFactory(factory.Factory):
    """
    Factory para criar etiquetas de missao (Etiqueta) de teste.

    Uso:
        etiqueta = EtiquetaFactory()
        etiqueta_custom = EtiquetaFactory(
            nome='Urgente',
            cor='#FF0000',
            descricao='Missoes urgentes'
        )
    """

    class Meta:
        model = Etiqueta

    nome = factory.Sequence(lambda n: f'Etiqueta {n}')
    cor = factory.fuzzy.FuzzyChoice(['#FF0000', '#00FF00', '#0000FF'])
    descricao = factory.Sequence(lambda n: f'Descricao etiqueta {n}')
