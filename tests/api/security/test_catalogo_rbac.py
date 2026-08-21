"""O catálogo `rbac-resources.json` tem que refletir os call sites reais.

É metade de um contrato entre repositórios independentes: aqui a `api`
promete que o JSON versionado descreve os gates que ela de fato aplica; no
`client`, `tests/rbac/check.mjs` cobra que todo recurso citado na UI exista
nesse JSON.

Sem os dois lados, nome errado no front some com o botão em silêncio
(`PermBased` falha fechado, admin bypassa o gate e não vê). Foi assim que
`esfaer`, `etp_mis` e `operacoes.etapa` sobreviveram, e que um rename
esqueceu 22 call sites com a forma `resource={"x"}`.

Estes testes não sobem banco nem cliente HTTP: leem código-fonte.
"""

import json
import pathlib
import re

from fcontrol_api.schemas.security.security import RESOURCE_PATTERN
from scripts.rbac_catalog import (
    CATALOGO,
    GUARDS,
    RAIZ,
    SEM_GATE_BACKEND,
    extrai_recursos,
)

ACOES_VALIDAS = {'view', 'create', 'update', 'delete'}


def _catalogo() -> dict:
    return json.loads(CATALOGO.read_text())


def test_catalogo_versionado_esta_em_dia():
    """Gate novo sem `uv run task rbac:export` reprova aqui."""
    vivos = extrai_recursos(RAIZ / 'fcontrol_api')

    assert _catalogo()['recursos'] == vivos, (
        'rbac-resources.json divergiu dos call sites. '
        'Rode `uv run task rbac:export` e commite o JSON '
        '(inclusive a cópia em client/tests/rbac/).'
    )


def test_copia_do_client_identica():
    """A cópia do front é o contrato; divergir dela é o bug que queremos."""
    copia = RAIZ.parent / 'client' / 'tests' / 'rbac' / 'resources.json'
    if not copia.exists():
        # Repos independentes: em clone isolado da `api` o front não está
        # no disco. Não é falha — o check do front roda no lint dele.
        return

    assert json.loads(copia.read_text()) == _catalogo(), (
        'client/tests/rbac/resources.json está defasado em relação a '
        'api/rbac-resources.json. Rode `uv run task rbac:export`.'
    )


def test_nomes_seguem_a_convencao():
    """Mesmo padrão que `ResourceCreate` cobra na criação pela tela.

    Reusa `RESOURCE_PATTERN` de propósito: recurso cadastrado pela tela e
    recurso citado no código têm que obedecer à MESMA regra, senão a
    convenção volta a ter duas fontes — que foi como a base acumulou
    quatro convenções ao mesmo tempo.
    """
    padrao = re.compile(RESOURCE_PATTERN)
    fora = [
        nome
        for nome in list(_catalogo()['recursos']) + list(SEM_GATE_BACKEND)
        if not padrao.match(nome)
    ]

    assert not fora, f'nome de recurso fora da convenção: {fora}'


def test_acoes_conhecidas():
    """Ação nova é decisão de projeto, não digitação — pega typo de `updat`."""
    desconhecidas = {
        f'{recurso}.{acao}'
        for recurso, acoes in _catalogo()['recursos'].items()
        for acao in acoes
        if acao not in ACOES_VALIDAS
    }

    assert not desconhecidas, (
        f'ação fora de {sorted(ACOES_VALIDAS)}: {sorted(desconhecidas)}. '
        'Se for deliberada, inclua em ACOES_VALIDAS.'
    )


def test_sem_gate_backend_nao_tem_gate_de_verdade():
    """A lista de exceções não pode acumular entrada que já foi resolvida.

    Se alguém gatear `estatistica.sebo` no backend, a justificativa aqui
    vira mentira — e a próxima pessoa a ler acredita nela.
    """
    vivos = set(extrai_recursos(RAIZ / 'fcontrol_api'))
    obsoletos = sorted(set(SEM_GATE_BACKEND) & vivos)

    assert not obsoletos, (
        f'{obsoletos} já tem gate no backend: remova de SEM_GATE_BACKEND '
        'em scripts/rbac_catalog.py.'
    )


def test_toda_excecao_tem_justificativa():
    vazias = [k for k, v in SEM_GATE_BACKEND.items() if len(v.strip()) < 40]

    assert not vazias, (
        f'{vazias} entrou em SEM_GATE_BACKEND sem justificativa real. '
        'Deixar a API aberta é decisão, não atalho.'
    )


def test_guards_conhecidos_ainda_existem():
    """Assinatura nova de guard sem atualizar GUARDS zera o catálogo calado.

    O extrator casa por nome e por POSIÇÃO do argumento. Se um guard for
    renomeado, ele simplesmente para de achar os call sites — e o JSON
    encolhe sem ninguém notar.
    """
    fonte = (RAIZ / 'fcontrol_api' / 'security.py').read_text()
    ausentes = [g for g in GUARDS if f'def {g}(' not in fonte]

    assert not ausentes, (
        f'guards {ausentes} não existem mais em security.py: '
        'atualize GUARDS em scripts/rbac_catalog.py.'
    )


def test_catalogo_nao_esta_vazio():
    """Rede contra o extrator quebrar e passar verde com zero achados."""
    assert len(_catalogo()['recursos']) > 20


def test_scripts_e_pacote_importavel():
    """`from scripts.rbac_catalog import ...` depende do pythonpath='.'."""
    assert pathlib.Path(RAIZ / 'scripts' / 'rbac_catalog.py').exists()
