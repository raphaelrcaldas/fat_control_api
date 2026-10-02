import pytest
from pydantic import ValidationError

from fcontrol_api.schemas.ops.om import (
    EtapaCreate,
    EtapaOut,
    OrdemMissaoUpdate,
)

BASE_ETAPA = {
    'dt_dep': '2026-10-02T10:00:00',
    'dt_arr': '2026-10-02T11:00:00',
    'origem': 'SBGL',
    'dest': 'SBBR',
    'alternativa': 'SBGO',
    'tvoo_alt': 30,
    'qtd_comb': 15,
}


@pytest.mark.parametrize(
    'texto',
    [
        '  PEO  APOIO  ',
        '\tPEO  APOIO\n',
        '\u00a0PEO  APOIO\u00a0',
        'PEO\tAPOIO',
        'PEO\u00a0APOIO',
        'PEO APOIO',
        'PEO\u0085APOIO',
        '\ufeffPEO\ufeff APOIO\ufeff',
        'PEO\u001cAPOIO',
    ],
)
def test_etapa_limpa_extremidades_e_compacta_espacos_internos(texto):
    etapa = EtapaCreate(**BASE_ETAPA, esf_aer=texto)
    assert etapa.esf_aer == 'PEO APOIO'


@pytest.mark.parametrize(
    'texto', ['', '  ', '\t\n\u00a0', '\u0085', '\ufeff', '\u001c']
)
def test_etapa_rejeita_esforco_aereo_vazio(texto):
    with pytest.raises(ValidationError) as exc_info:
        EtapaCreate(**BASE_ETAPA, esf_aer=texto)
    assert exc_info.value.errors()[0]['loc'] == ('esf_aer',)


def test_update_normaliza_etapas_aninhadas():
    update = OrdemMissaoUpdate(
        etapas=[{**BASE_ETAPA, 'esf_aer': '  PEO  /  SPMAS / FAB-TAL  '}]
    )
    assert update.etapas[0].esf_aer == 'PEO / SPMAS / FAB-TAL'


def test_resposta_normaliza_valor_legado_sem_exigir_campo_preenchido():
    etapa = EtapaOut(
        **BASE_ETAPA,
        id=1,
        ordem_id=1,
        tvoo_etp=60,
        esf_aer='  PEO  /  SPMAS / FAB-TAL  ',
    )
    assert etapa.esf_aer == 'PEO / SPMAS / FAB-TAL'
    etapa_legada_vazia = EtapaOut(
        **BASE_ETAPA, id=2, ordem_id=1, tvoo_etp=60, esf_aer='  '
    )
    assert not etapa_legada_vazia.esf_aer
