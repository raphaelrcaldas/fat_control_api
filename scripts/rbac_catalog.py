"""Catálogo de recursos RBAC — extrai dos call sites e exporta em JSON.

Existe porque o nome de recurso é a única parte do RBAC que **não** tem
verificação nenhuma: o backend cita uma string, o front cita outra, e
`PermBased` falha fechado — o botão some em vez de dar erro. Como admin
bypassa o gate, quem desenvolve nunca vê. Já viveram assim `esfaer`,
`etp_mis`, `operacoes.etapa` e 22 call sites no `client` que um rename
deixou para trás.

O JSON gerado é o contrato entre repositórios independentes: `api/` produz,
os fronts consomem no lint. Regenerar com `uv run task rbac:export` sempre
que um gate novo entrar — o `test_catalogo_rbac.py` reprova se esquecer.

Extrai pelo **ponto de uso**, nunca por busca de string solta: `users`,
`trips` e `etapas` também são segmento de rota, chave de query e nome de
tabela.
"""

import argparse
import ast
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CATALOGO = RAIZ / 'rbac-resources.json'

# Cada guard e o índice POSICIONAL do argumento `resource`. A checagem por
# posição é o que permite achar a chamada mesmo quebrada em várias linhas,
# e é por isso que assinatura nova exige uma linha aqui.
GUARDS = {
    'permission_checker': 0,
    'has_permission': 2,
    'has_org_permission': 3,
    'ensure_permission_or_owner': 2,
    'ensure_org_permission_or_owner': 3,
}

# Recurso que existe SÓ para esconder item de menu — nenhum endpoint o
# exige. Entrar aqui é declarar "a API atende qualquer token válido nesta
# área", que é a condição que deixou nove recursos sem gate por anos. Exige
# justificativa; na dúvida, o certo é criar o gate, não a linha.
SEM_GATE_BACKEND = {
    'estatistica.sebo': (
        'O FatBird consome /estatistica/sebo com token de tripulante, que '
        'não tem role — gatear tranca o portal. Escopo por ActiveOrg.'
    ),
    'instrucao.simulador': (
        '/cegep/missoes/simular é calculadora pura sobre tabelas de '
        'referência (não lê dado de org) e também roda no FatBird.'
    ),
    'ops.quadro': (
        'Tela de leitura composta, sem endpoint próprio: os dados vêm de '
        '/ops/om, já gateado por ops.ordem_missao.'
    ),
}


def _resolve(no: ast.AST, consts: dict[str, str]) -> str | None:
    """Literal, ou constante de módulo (`PROPOSTA`, `IMG_RESOURCE`)."""
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    if isinstance(no, ast.Name):
        return consts.get(no.id)
    return None


def extrai_recursos(pacote: pathlib.Path) -> dict[str, list[str]]:
    """`{recurso: [ações]}` a partir de todo call site de guard no pacote."""
    achados: dict[str, set[str]] = {}

    for arquivo in sorted(pacote.rglob('*.py')):
        arvore = ast.parse(arquivo.read_text(), filename=str(arquivo))

        # Constantes de módulo primeiro: `PROPOSTA = 'cegep.comiss.propostas'`
        # é citada por nome nos Depends logo abaixo.
        consts: dict[str, str] = {}
        for no in arvore.body:
            if isinstance(no, ast.Assign) and len(no.targets) == 1:
                alvo = no.targets[0]
                valor = no.value
                if (
                    isinstance(alvo, ast.Name)
                    and isinstance(valor, ast.Constant)
                    and isinstance(valor.value, str)
                ):
                    consts[alvo.id] = valor.value

        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue

            fn = no.func
            nome = fn.attr if isinstance(fn, ast.Attribute) else None
            if isinstance(fn, ast.Name):
                nome = fn.id
            if nome not in GUARDS:
                continue

            idx = GUARDS[nome]
            recurso = acao = None

            if len(no.args) > idx + 1:
                recurso = _resolve(no.args[idx], consts)
                acao = _resolve(no.args[idx + 1], consts)

            for kw in no.keywords:
                if kw.arg == 'resource':
                    recurso = _resolve(kw.value, consts)
                elif kw.arg == 'action':
                    acao = _resolve(kw.value, consts)

            if recurso and acao:
                achados.setdefault(recurso, set()).add(acao)

    return {r: sorted(a) for r, a in sorted(achados.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--check',
        action='store_true',
        help='não escreve; sai 1 se o JSON versionado estiver defasado',
    )
    args = parser.parse_args()

    recursos = extrai_recursos(RAIZ / 'fcontrol_api')
    conteudo = json.dumps(
        {
            '_comentario': (
                'Gerado por `uv run task rbac:export`. Não editar à mão — '
                'a fonte são os call sites de guard em fcontrol_api/. '
                'Copiar para os fronts ao adicionar recurso.'
            ),
            'recursos': recursos,
            'sem_gate_backend': SEM_GATE_BACKEND,
        },
        indent=2,
        ensure_ascii=False,
    )

    if args.check:
        atual = CATALOGO.read_text() if CATALOGO.exists() else ''
        if atual.rstrip('\n') != conteudo:
            print(
                'rbac-resources.json defasado. '
                'Rode `uv run task rbac:export`.',
                file=sys.stderr,
            )
            return 1
        print('rbac-resources.json em dia.')
        return 0

    CATALOGO.write_text(conteudo + '\n')
    print(f'{len(recursos)} recursos -> {CATALOGO.relative_to(RAIZ)}')

    # Os fronts são repos independentes, mas moram lado a lado no disco:
    # atualizar a cópia aqui evita o passo manual mais fácil de esquecer.
    # Ausente (CI, clone isolado), simplesmente não faz nada.
    for front in ('client',):
        rel = f'{front}/tests/rbac/resources.json'
        destino = RAIZ.parent / rel
        if destino.parent.exists():
            destino.write_text(conteudo + '\n')
            print(f'{len(recursos)} recursos -> ../{rel}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
