"""Exporta as concessões de RBAC (role -> permissões) do banco apontado.

READ-ONLY. Alimenta o relatório `npm run rbac:matriz` do `client`, que
cruza estas concessões com o inventário de elementos gateados da UI e
responde "o que a role X de fato enxerga?" — pergunta que hoje só se
responde clicando.

Por que é EXPORT e não teste: concessão é dado por ambiente. DEV e PROD
divergem legitimamente, e alguém editando uma role pela tela /admin/roles
mudaria o resultado sem nenhum commit. Assert em cima disso falharia por
motivo que não é defeito. Por isso o artefato não é versionado.

Uso:
    cd api
    uv run python -m scripts.rbac_grants                     # DEV (.env)
    DATABASE_URL="<prod>" uv run python -m scripts.rbac_grants

O arquivo sai em `../client/tests/rbac/.grants.json` quando o front está
no disco (gitignored), e sempre em `api/.grants.json`.
"""

import asyncio
import json
import pathlib

from sqlalchemy import select

from fcontrol_api.database import get_session
from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
)

RAIZ = pathlib.Path(__file__).resolve().parent.parent


async def _coletar() -> dict[str, list[str]]:
    async for session in get_session():
        linhas = await session.execute(
            select(Roles.name, Resources.name, Permissions.name)
            .select_from(Roles)
            .join(RolePermissions, RolePermissions.role_id == Roles.id)
            .join(
                Permissions,
                Permissions.id == RolePermissions.permission_id,
            )
            .join(Resources, Resources.id == Permissions.resource_id)
        )

        concessoes: dict[str, set[str]] = {}
        for role, recurso, acao in linhas:
            concessoes.setdefault(role, set()).add(f'{recurso}.{acao}')

        # Role sem nenhuma concessão precisa aparecer na matriz como linha
        # vazia — some do JOIN acima, e some silenciosamente do relatório.
        todas = await session.scalars(select(Roles.name))
        for role in todas:
            concessoes.setdefault(role, set())

        return {r: sorted(p) for r, p in sorted(concessoes.items())}

    raise RuntimeError('sessão de banco não foi aberta')


def main() -> int:
    concessoes = asyncio.run(_coletar())

    conteudo = json.dumps(
        {
            '_comentario': (
                'Gerado por `uv run python -m scripts.rbac_grants`. '
                'Dado POR AMBIENTE — não versionar, não usar em assert.'
            ),
            'concessoes': concessoes,
        },
        indent=2,
        ensure_ascii=False,
    )

    destinos = [RAIZ / '.grants.json']
    copia = RAIZ.parent / 'client' / 'tests' / 'rbac' / '.grants.json'
    if copia.parent.exists():
        destinos.append(copia)

    for destino in destinos:
        destino.write_text(conteudo + '\n')
        print(f'{len(concessoes)} roles -> {destino}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
