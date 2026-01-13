import base64
from datetime import datetime, timedelta
from http import HTTPStatus
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException, Request
from jwt import decode

from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.resources import Roles, UserRole
from fcontrol_api.security import (
    create_access_token,
    get_current_user,
    get_password_hash,
    permission_checker,
    require_admin,
    settings,
)
from tests.factories import UserFactory


def create_user_from_factory(saram: int) -> User:
    """Helper para criar User do factory"""
    user_data = UserFactory.build(saram=saram)
    return User(
        p_g=user_data.p_g,
        esp=user_data.esp,
        nome_guerra=user_data.nome_guerra,
        nome_completo=user_data.nome_completo,
        id_fab=user_data.id_fab,
        saram=user_data.saram,
        unidade=user_data.unidade,
        cpf=user_data.cpf,
        email_fab=user_data.email_fab,
        email_pess=user_data.email_pess,
        nasc=user_data.nasc,
        ult_promo=user_data.ult_promo,
        password=get_password_hash(user_data.password),
        ant_rel=user_data.ant_rel,
    )


# Linha 63: create_access_token com dev=True
def test_create_access_token_dev_mode():
    """Testa criação de token com dev=True (10 anos de expiração)"""
    MAX_TIME_DIFF_SECONDS = 5  # Tolerância de tempo em segundos

    data = {'user_id': 1, 'sub': 'test user'}
    token = create_access_token(data, dev=True)

    secret_key = base64.urlsafe_b64decode(settings.SECRET_KEY + '========')
    decoded = decode(token, secret_key, algorithms=[settings.ALGORITHM])

    # Verificar expiração em ~10 anos
    exp_time = datetime.fromtimestamp(decoded['exp'], tz=ZoneInfo('UTC'))
    now = datetime.now(tz=ZoneInfo('UTC'))
    expected_exp = now + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES, days=3650
    )

    # Permitir tolerância de tempo
    time_diff = abs((exp_time - expected_exp).total_seconds())
    assert time_diff < MAX_TIME_DIFF_SECONDS, (
        f'Diferença de tempo: {time_diff}s'
    )


# Linha 77: get_current_user sem user_id no request.state
@pytest.mark.anyio
async def test_get_current_user_no_user_id_in_state(session):
    """Testa raise quando não tem user_id no request.state"""
    mock_request = Mock(spec=Request)
    mock_request.state = Mock()

    # Garantir que user_id não existe no state
    if hasattr(mock_request.state, 'user_id'):
        delattr(mock_request.state, 'user_id')

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_request, session)

    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert exc_info.value.detail == 'Não autenticado'


# Linha 88: get_current_user com usuário não encontrado
@pytest.mark.anyio
async def test_get_current_user_user_not_found(session):
    """Testa raise quando usuário não existe no banco"""
    mock_request = Mock(spec=Request)
    mock_request.state = Mock()
    mock_request.state.user_id = 99999  # ID inexistente

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_request, session)

    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert exc_info.value.detail == 'Usuário não encontrado'


# Linha 94: get_current_user com usuário inativo
@pytest.mark.anyio
async def test_get_current_user_inactive_user(session):
    """Testa raise quando usuário está inativo"""
    user = create_user_from_factory(saram=999999)
    session.add(user)
    await session.flush()

    # Marcar como inativo
    user.active = False
    await session.flush()

    mock_request = Mock(spec=Request)
    mock_request.state = Mock()
    mock_request.state.user_id = user.id
    mock_request.state.app_client = None

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_request, session)

    assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
    assert exc_info.value.detail == 'Usuário inativo'


# Linhas 119-130: require_admin com sucesso
@pytest.mark.anyio
async def test_require_admin_success(session):
    """Testa require_admin quando usuário é admin"""
    user = create_user_from_factory(saram=888888)
    session.add(user)
    await session.flush()

    # Criar role admin
    admin_role = Roles(name='admin', description='Administrator')
    session.add(admin_role)
    await session.flush()

    # Atribuir role ao usuário
    user_role = UserRole(user_id=user.id, role_id=admin_role.id)
    session.add(user_role)
    await session.flush()

    # Testar
    result = await require_admin(session, user)
    assert result == user


# Linhas 119-130: require_admin quando usuário não é admin
@pytest.mark.anyio
async def test_require_admin_user_not_admin(session):
    """Testa require_admin quando usuário não é admin"""
    user = create_user_from_factory(saram=777777)
    session.add(user)
    await session.flush()

    # Criar role não-admin
    user_role_obj = Roles(name='user', description='Regular user')
    session.add(user_role_obj)
    await session.flush()

    # Atribuir role ao usuário
    user_role = UserRole(user_id=user.id, role_id=user_role_obj.id)
    session.add(user_role)
    await session.flush()

    # Testar
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(session, user)

    assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
    assert exc_info.value.detail == 'Permissão negada'


# Linhas 119-130: require_admin quando usuário não tem role
@pytest.mark.anyio
async def test_require_admin_no_role(session):
    """Testa require_admin quando usuário não tem role"""
    user = create_user_from_factory(saram=666666)
    session.add(user)
    await session.flush()

    # Testar
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(session, user)

    assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
    assert exc_info.value.detail == 'Permissão negada'


# Linha 144: permission_checker quando user_data é None
@pytest.mark.anyio
async def test_permission_checker_user_data_none(session):
    """Testa raise quando get_user_roles retorna None"""
    user = create_user_from_factory(saram=555555)
    session.add(user)
    await session.flush()

    # Mock get_user_roles para retornar None
    with patch(
        'fcontrol_api.security.get_user_roles',
        new_callable=AsyncMock,
    ) as mock_get_user_roles:
        mock_get_user_roles.return_value = None

        # Criar checker
        checker = permission_checker('users', 'read')

        # Testar
        with pytest.raises(HTTPException) as exc_info:
            await checker(session, user)

        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
        assert 'sem role atribuída' in exc_info.value.detail
        mock_get_user_roles.assert_called_once_with(user.id, session)


# Linha 144: permission_checker quando user_data é dict vazio (falsy)
@pytest.mark.anyio
async def test_permission_checker_user_data_empty_dict(session):
    """Testa raise quando get_user_roles retorna dict vazio"""
    user = create_user_from_factory(saram=444444)
    session.add(user)
    await session.flush()

    # Mock get_user_roles para retornar dict vazio (falsy)
    with patch(
        'fcontrol_api.security.get_user_roles',
        new_callable=AsyncMock,
    ) as mock_get_user_roles:
        mock_get_user_roles.return_value = {}

        # Criar checker
        checker = permission_checker('users', 'write')

        # Testar
        with pytest.raises(HTTPException) as exc_info:
            await checker(session, user)

        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
        assert 'sem role atribuída' in exc_info.value.detail
