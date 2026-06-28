"""Testes para a integridade do cache de custos.

`integridade.py` é a fonte única da chave canônica `pg_<valor>_sit_<valor>`
e do hash de drift dos inputs. Estes testes blindam a rede de segurança que
impede a leitura de produzir dinheiro errado quando o cache está defasado em
relação aos militares/pernoites atuais da missão.
"""

from datetime import date

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.cegep.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.services.custos.integridade import (
    chave_pg_sit,
    gerar_hash_custos,
    verificar_integridade_custos,
)


def _frag(acrec_desloc=False):
    return CustoFragMisInput(acrec_desloc=acrec_desloc)


def _user(p_g=PostoGradEnum.CP, sit='c'):
    return CustoUserFragInput(p_g=p_g, sit=sit)


def _pernoite(
    id=1,
    data_ini=date(2026, 2, 1),
    data_fim=date(2026, 2, 3),
    meia_diaria=False,
    acrec_desloc=False,
    cidade_codigo=3550308,
):
    return CustoPernoiteInput(
        id=id,
        data_ini=data_ini,
        data_fim=data_fim,
        meia_diaria=meia_diaria,
        acrec_desloc=acrec_desloc,
        cidade_codigo=cidade_codigo,
    )


# --- chave_pg_sit ---


def test_chave_pg_sit_com_string():
    """String simples produz a chave canônica."""
    assert chave_pg_sit('3s', 'c') == 'pg_3s_sit_c'


def test_chave_pg_sit_com_enum_usa_value():
    """Enum é normalizado para .value (evita 'PostoGradEnum.S3').

    Este é o bug histórico que motivou a fonte única: na mesma sessão de
    escrita o ORM pode conter o enum, e f'{enum}' geraria a chave errada.
    """
    chave = chave_pg_sit(PostoGradEnum.CP, 'g')
    assert chave == f'pg_{PostoGradEnum.CP.value}_sit_g'
    assert 'PostoGradEnum' not in chave


def test_chave_pg_sit_enum_e_string_coincidem():
    """Escrita (enum) e leitura (str) geram exatamente a mesma chave."""
    assert chave_pg_sit(PostoGradEnum.CP, 'c') == chave_pg_sit(
        PostoGradEnum.CP.value, 'c'
    )


# --- gerar_hash_custos: determinismo ---


def test_hash_deterministico_mesmos_inputs():
    """Mesmos inputs sempre produzem o mesmo hash."""
    frag = _frag()
    users = [_user()]
    pernoites = [_pernoite()]

    h1 = gerar_hash_custos(frag, users, pernoites)
    h2 = gerar_hash_custos(frag, users, pernoites)

    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_hash_independe_da_ordem_dos_militares():
    """Militares entram como conjunto: ordem não altera o hash."""
    frag = _frag()
    pernoites = [_pernoite()]
    users_ab = [_user(PostoGradEnum.CP, 'c'), _user(PostoGradEnum.CB, 'c')]
    users_ba = [_user(PostoGradEnum.CB, 'c'), _user(PostoGradEnum.CP, 'c')]

    assert gerar_hash_custos(frag, users_ab, pernoites) == gerar_hash_custos(
        frag, users_ba, pernoites
    )


def test_hash_ignora_militares_duplicados():
    """Militar repetido (mesmo p_g+sit) não altera a integridade."""
    frag = _frag()
    pernoites = [_pernoite()]
    unico = [_user(PostoGradEnum.CP, 'c')]
    duplicado = [_user(PostoGradEnum.CP, 'c'), _user(PostoGradEnum.CP, 'c')]

    assert gerar_hash_custos(frag, unico, pernoites) == gerar_hash_custos(
        frag, duplicado, pernoites
    )


def test_hash_independe_da_ordem_dos_pernoites():
    """Pernoites são ordenados internamente: ordem de entrada não importa."""
    frag = _frag()
    users = [_user()]
    p1 = _pernoite(id=1, data_ini=date(2026, 2, 1), data_fim=date(2026, 2, 3))
    p2 = _pernoite(id=2, data_ini=date(2026, 2, 3), data_fim=date(2026, 2, 5))

    assert gerar_hash_custos(frag, users, [p1, p2]) == gerar_hash_custos(
        frag, users, [p2, p1]
    )


# --- gerar_hash_custos: sensibilidade a mudanças (detecção de drift) ---


def test_hash_muda_com_acrec_desloc():
    """Alterar acréscimo de deslocamento da missão muda o hash."""
    users = [_user()]
    pernoites = [_pernoite()]

    h_sem = gerar_hash_custos(_frag(False), users, pernoites)
    h_com = gerar_hash_custos(_frag(True), users, pernoites)

    assert h_sem != h_com


def test_hash_muda_com_situacao_do_militar():
    """Trocar sit ('c' -> 'g') muda o hash (custo é totalmente diferente)."""
    frag = _frag()
    pernoites = [_pernoite()]

    h_c = gerar_hash_custos(frag, [_user(sit='c')], pernoites)
    h_g = gerar_hash_custos(frag, [_user(sit='g')], pernoites)

    assert h_c != h_g


def test_hash_muda_com_posto_graduacao():
    """Trocar o posto/graduação muda o hash."""
    frag = _frag()
    pernoites = [_pernoite()]

    h_cp = gerar_hash_custos(frag, [_user(PostoGradEnum.CP)], pernoites)
    h_cb = gerar_hash_custos(frag, [_user(PostoGradEnum.CB)], pernoites)

    assert h_cp != h_cb


def test_hash_muda_com_datas_do_pernoite():
    """Alterar as datas de um pernoite muda o hash."""
    frag = _frag()
    users = [_user()]

    h_orig = gerar_hash_custos(frag, users, [_pernoite()])
    h_novo = gerar_hash_custos(
        frag, users, [_pernoite(data_fim=date(2026, 2, 10))]
    )

    assert h_orig != h_novo


def test_hash_muda_com_meia_diaria():
    """Alternar meia-diária muda o hash."""
    frag = _frag()
    users = [_user()]

    h_sem = gerar_hash_custos(frag, users, [_pernoite(meia_diaria=False)])
    h_com = gerar_hash_custos(frag, users, [_pernoite(meia_diaria=True)])

    assert h_sem != h_com


def test_hash_muda_com_cidade():
    """Trocar a cidade do pernoite (muda grupo) muda o hash."""
    frag = _frag()
    users = [_user()]

    h_sp = gerar_hash_custos(frag, users, [_pernoite(cidade_codigo=3550308)])
    h_out = gerar_hash_custos(frag, users, [_pernoite(cidade_codigo=9999999)])

    assert h_sp != h_out


# --- verificar_integridade_custos ---


def test_integridade_sem_cache_sem_pernoites():
    """Sem cache e sem pernoites: íntegro (missão sem custo)."""
    assert (
        verificar_integridade_custos(_frag(), [_user()], [], None) is True
    )


def test_integridade_sem_cache_com_pernoites():
    """Sem cache mas com pernoites: NÃO íntegro (recálculo pendente)."""
    assert (
        verificar_integridade_custos(_frag(), [_user()], [_pernoite()], None)
        is False
    )


def test_integridade_cache_vazio_dict_com_pernoites():
    """Cache {} (dict vazio) com pernoites: NÃO íntegro."""
    assert (
        verificar_integridade_custos(_frag(), [_user()], [_pernoite()], {})
        is False
    )


def test_integridade_cache_tipo_invalido():
    """Cache não-dict (ex.: string) cai no ramo de cache ausente."""
    assert (
        verificar_integridade_custos(
            _frag(), [_user()], [_pernoite()], 'invalido'
        )
        is False
    )


def test_integridade_cache_legado_sem_input_hash():
    """Cache legado sem `_input_hash`: tratado como íntegro (sem base)."""
    cache = {'total_dias': 2, 'totais_pg_sit': {}}
    assert (
        verificar_integridade_custos(_frag(), [_user()], [_pernoite()], cache)
        is True
    )


def test_integridade_hash_correspondente():
    """Hash armazenado igual ao recomputado: íntegro."""
    frag, users, pernoites = _frag(), [_user()], [_pernoite()]
    hash_ok = gerar_hash_custos(frag, users, pernoites)
    cache = {'_input_hash': hash_ok}

    assert (
        verificar_integridade_custos(frag, users, pernoites, cache) is True
    )


def test_integridade_drift_hash_divergente():
    """Inputs mudaram após a escrita: hash diverge -> NÃO íntegro.

    Simula uma edição da missão (pernoite estendido) sem recálculo do cache.
    """
    frag, users = _frag(), [_user()]
    pernoites_antigos = [_pernoite(data_fim=date(2026, 2, 3))]
    hash_antigo = gerar_hash_custos(frag, users, pernoites_antigos)
    cache = {'_input_hash': hash_antigo}

    pernoites_novos = [_pernoite(data_fim=date(2026, 2, 10))]
    assert (
        verificar_integridade_custos(frag, users, pernoites_novos, cache)
        is False
    )
