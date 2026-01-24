import asyncio
import os
import pathlib
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.security import create_access_token
from tests.factories import UserFactory
from tests.seed import ALL_SEED_OBJECTS


async def seed():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print('❌ DATABASE_URL não definida!')
        return

    print(f'🌱 Populando banco de dados: {database_url}')

    engine = create_async_engine(database_url)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        async with session.begin():
            # 1. Adiciona todos os objetos básicos de seed (Postos, Roles, etc)
            session.add_all(ALL_SEED_OBJECTS)

        await session.commit()

        async with session.begin():
            # 2. Cria Recursos e Permissões necessários para admin
            user_resource = Resources(
                name='user', description='Gerenciamento de Usuários'
            )
            session.add(user_resource)
            await session.flush()

            actions = ['create', 'read', 'update', 'delete']
            user_permissions = []
            for action in actions:
                perm = Permissions(
                    resource_id=user_resource.id,
                    name=action,
                    description=f'{action.capitalize()} users',
                )
                session.add(perm)
                user_permissions.append(perm)

            await session.flush()

            # 3. Busca a role 'admin' e vincula as permissões
            admin_role = await session.scalar(
                select(Roles).where(Roles.name == 'admin')
            )

            if not admin_role:
                print("❌ Role 'admin' não encontrada!")
                return

            for perm in user_permissions:
                session.add(
                    RolePermissions(
                        role_id=admin_role.id, permission_id=perm.id
                    )
                )

            # 4. Cria o usuário administrador dinâmico

            project_root = pathlib.Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            # Gera um admin aleatório mas funcional
            admin_user = UserFactory(first_login=False)
            session.add(admin_user)

            # Criando alguns usuários extras
            for i in range(10):
                session.add(UserFactory())

            await session.flush()
            await session.refresh(admin_user)

            # 5. Atribui a role de admin ao usuário
            user_role = UserRole(user_id=admin_user.id, role_id=admin_role.id)
            session.add(user_role)
            await session.commit()

            # 6. Gera o Token "da Factorie" (dinâmico)
            token_data = {
                'sub': f'{admin_user.posto.short} {admin_user.nome_guerra}',
                'user_id': admin_user.id,
                'app_client': 'fatcontrol',
            }
            token = create_access_token(data=token_data)

            # 7. Salva o token para o Playwright ler
            client_root = project_root.parent / 'client'
            with open(client_root / '.e2e_token', 'w', encoding='utf-8') as f:
                f.write(token)

    await engine.dispose()
    print('✅ Seed finalizado com sucesso (Token dinâmico gerado)!')


if __name__ == '__main__':
    asyncio.run(seed())
