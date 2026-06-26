"""Testes da camada de segurança (`fcontrol_api/security.py`).

Área sensível: cobre hashing de senha, PKCE, emissão de JWT e — o mais
crítico — as dependências de autorização escopadas por organização ativa
(`require_admin`, `require_system_admin`, `permission_checker`,
`has_org_permission`, `ensure_permission_or_owner`). Os testes usam dados
reais (roles/permissions/user_roles no banco de teste) em vez de mocks,
para exercitar de fato a resolução de vínculo por org e provar que
permissão/admin de uma unidade NÃO vaza para outra.
"""

import base64
import hashlib
from datetime import datetime, timedelta
from http import HTTPStatus
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from jwt import decode
from sqlalchemy import select

from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.models.shared.users import User
from fcontrol_api.security import (
    AdminScope,
    create_access_token,
    ensure_permission_or_owner,
    get_active_org,
    get_admin_scope,
    get_current_user,
    get_password_hash,
    has_org_permission,
    has_permission,
    permission_checker,
    require_active_org,
    require_admin,
    require_system_admin,
    settings,
    token_data,
    verify_password,
    verify_pkce_challenge,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.anyio


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_request(**state):
    """Request mínimo: só o `state` que as dependências leem.

    Omitir uma chave (ex.: `user_id`) reproduz fielmente o `hasattr`/
    `getattr(..., None)` que o código de produção faz.
    """
    return SimpleNamespace(state=SimpleNamespace(**state))


async def make_user(session, *, active=True, **overrides):
    """Persiste um User completo via factory (todos os campos do model)."""
    user = UserFactory.build(**overrides)
    user.active = active
    session.add(user)
    await session.flush()
    return user


async def reload_user(session, user):
    """Recarrega o User com `posto` (selectin) disponível para `token_data`."""
    return await session.scalar(select(User).where(User.id == user.id))


async def get_or_make_role(session, name):
    role = await session.scalar(select(Roles).where(Roles.name == name))
    if role is None:
        role = Roles(name=name, description=name)
        session.add(role)
        await session.flush()
    return role


async def bind_role(session, user, role_name, *, org=None):
    """Vincula `user` à role `role_name` na org `org` (None = sistema)."""
    role = await get_or_make_role(session, role_name)
    ur = UserRole(user_id=user.id, role_id=role.id, organizacao_id=org)
    session.add(ur)
    await session.flush()
    return ur


async def grant(session, role_name, resource, action, *, org=None, user=None):
    """Garante resource+permission+role_permission e vincula o user.

    Cria (idempotente) o recurso e a permissão `resource.action`, concede à
    role `role_name` e, se `user` for dado, vincula o user à role em `org`.
    """
    role = await get_or_make_role(session, role_name)

    res = await session.scalar(
        select(Resources).where(Resources.name == resource)
    )
    if res is None:
        res = Resources(name=resource, description=resource)
        session.add(res)
        await session.flush()

    perm = await session.scalar(
        select(Permissions).where(
            Permissions.resource_id == res.id, Permissions.name == action
        )
    )
    if perm is None:
        perm = Permissions(
            resource_id=res.id, name=action, description=action
        )
        session.add(perm)
        await session.flush()

    existing = await session.scalar(
        select(RolePermissions).where(
            RolePermissions.role_id == role.id,
            RolePermissions.permission_id == perm.id,
        )
    )
    if existing is None:
        session.add(
            RolePermissions(role_id=role.id, permission_id=perm.id)
        )
        await session.flush()

    if user is not None:
        await bind_role(session, user, role_name, org=org)
    return role


# --------------------------------------------------------------------------- #
# Hashing de senha
# --------------------------------------------------------------------------- #
class TestPasswordHashing:
    def test_hash_differs_from_plaintext(self):
        h = get_password_hash('s3nha-secreta')
        assert h != 's3nha-secreta'
        assert isinstance(h, str)

    def test_verify_accepts_correct_password(self):
        h = get_password_hash('correta')
        assert verify_password('correta', h) is True

    def test_verify_rejects_wrong_password(self):
        h = get_password_hash('correta')
        assert verify_password('errada', h) is False

    def test_hash_is_salted(self):
        """Dois hashes da mesma senha diferem, mas ambos verificam."""
        h1 = get_password_hash('mesma')
        h2 = get_password_hash('mesma')
        assert h1 != h2
        assert verify_password('mesma', h1)
        assert verify_password('mesma', h2)


# --------------------------------------------------------------------------- #
# PKCE
# --------------------------------------------------------------------------- #
class TestPkceChallenge:
    def _challenge_for(self, verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()

    def test_valid_pair_matches(self):
        verifier = 'verifier-aleatorio-suficientemente-longo-1234567890'
        challenge = self._challenge_for(verifier)
        assert verify_pkce_challenge(verifier, challenge) is True

    def test_wrong_verifier_rejected(self):
        verifier = 'verifier-aleatorio-suficientemente-longo-1234567890'
        challenge = self._challenge_for(verifier)
        assert verify_pkce_challenge('outro-verifier', challenge) is False


# --------------------------------------------------------------------------- #
# token_data
# --------------------------------------------------------------------------- #
class TestTokenData:
    async def test_builds_expected_payload(self, session):
        user = await make_user(session, first_login=False)
        user = await reload_user(session, user)

        data = token_data(user, 'fatcontrol')

        assert data['user_id'] == user.id
        assert data['sub'] == f'{user.posto.short} {user.nome_guerra}'
        assert data['app_client'] == 'fatcontrol'
        assert data['first_login'] is False
        assert data['active_org'] is None

    async def test_includes_active_org_when_given(self, session):
        user = await make_user(session)
        user = await reload_user(session, user)

        data = token_data(user, 'fatcontrol', active_org='11gt')

        assert data['active_org'] == '11gt'


# --------------------------------------------------------------------------- #
# create_access_token
# --------------------------------------------------------------------------- #
class TestCreateAccessToken:
    TOLERANCE_SECONDS = 5

    def _decode(self, tok):
        secret = base64.urlsafe_b64decode(settings.SECRET_KEY + '========')
        return decode(tok, secret, algorithms=[settings.ALGORITHM])

    def _assert_expires_in(self, tok, minutes, extra_days=0):
        decoded = self._decode(tok)
        exp = datetime.fromtimestamp(decoded['exp'], tz=ZoneInfo('UTC'))
        expected = datetime.now(tz=ZoneInfo('UTC')) + timedelta(
            minutes=minutes, days=extra_days
        )
        diff = abs((exp - expected).total_seconds())
        assert diff < self.TOLERANCE_SECONDS, f'diff={diff}s'

    def test_normal_expiry(self):
        tok = create_access_token({'user_id': 1, 'sub': 'x'})
        self._assert_expires_in(tok, settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    def test_first_login_uses_short_expiry(self):
        tok = create_access_token({'user_id': 1, 'first_login': True})
        self._assert_expires_in(
            tok, settings.FIRST_LOGIN_TOKEN_EXPIRE_MINUTES
        )

    def test_dev_mode_extends_ten_years(self):
        tok = create_access_token({'user_id': 1}, dev=True)
        self._assert_expires_in(
            tok, settings.ACCESS_TOKEN_EXPIRE_MINUTES, extra_days=3650
        )

    def test_payload_roundtrip(self):
        tok = create_access_token({'user_id': 42, 'sub': 'cb fulano'})
        decoded = self._decode(tok)
        assert decoded['user_id'] == 42
        assert decoded['sub'] == 'cb fulano'

    def test_does_not_mutate_input_dict(self):
        data = {'user_id': 1}
        create_access_token(data)
        assert 'exp' not in data


# --------------------------------------------------------------------------- #
# get_current_user
# --------------------------------------------------------------------------- #
class TestGetCurrentUser:
    async def test_missing_user_id_raises_401(self, session):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(make_request(), session)
        assert exc.value.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.value.detail == 'Não autenticado'

    async def test_user_not_found_raises_401(self, session):
        req = make_request(user_id=999999, app_client=None)
        with pytest.raises(HTTPException) as exc:
            await get_current_user(req, session)
        assert exc.value.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.value.detail == 'Usuário não encontrado'

    async def test_inactive_user_raises_403(self, session):
        user = await make_user(session, active=False)
        req = make_request(user_id=user.id, app_client=None)
        with pytest.raises(HTTPException) as exc:
            await get_current_user(req, session)
        assert exc.value.status_code == HTTPStatus.FORBIDDEN
        assert exc.value.detail == 'Usuário inativo'

    async def test_success_sets_current_user(self, session):
        user = await make_user(session)
        req = make_request(user_id=user.id, app_client=None)

        result = await get_current_user(req, session)

        assert result.id == user.id
        assert req.state.current_user.id == user.id

    async def test_fatcontrol_without_role_forbidden(self, session):
        """app_client exige validação de acesso: sem role, 403."""
        user = await make_user(session)
        req = make_request(user_id=user.id, app_client='fatcontrol')
        with pytest.raises(HTTPException) as exc:
            await get_current_user(req, session)
        assert exc.value.status_code == HTTPStatus.FORBIDDEN

    async def test_fatcontrol_with_role_succeeds(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'user')
        req = make_request(user_id=user.id, app_client='fatcontrol')

        result = await get_current_user(req, session)

        assert result.id == user.id


# --------------------------------------------------------------------------- #
# require_admin (admin escopado à org ativa)
# --------------------------------------------------------------------------- #
class TestRequireAdmin:
    async def test_system_admin_with_no_active_org(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'admin', org=None)
        req = make_request(active_org=None)

        result = await require_admin(req, session, user)

        assert result is user

    async def test_org_admin_with_matching_active_org(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'admin', org='11gt')
        req = make_request(active_org='11gt')

        result = await require_admin(req, session, user)

        assert result is user

    async def test_scope_mismatch_system_admin_in_org(self, session):
        """Admin de sistema (org None) numa unidade ativa → SCOPE_FORBIDDEN."""
        user = await make_user(session)
        await bind_role(session, user, 'admin', org=None)
        req = make_request(active_org='11gt')

        with pytest.raises(HTTPException) as exc:
            await require_admin(req, session, user)
        assert exc.value.detail == 'SCOPE_FORBIDDEN'

    async def test_admin_of_other_org_forbidden(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'admin', org='1gt')
        req = make_request(active_org='11gt')

        with pytest.raises(HTTPException) as exc:
            await require_admin(req, session, user)
        assert exc.value.detail == 'SCOPE_FORBIDDEN'

    async def test_non_admin_forbidden(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'user', org='11gt')
        req = make_request(active_org='11gt')

        with pytest.raises(HTTPException) as exc:
            await require_admin(req, session, user)
        assert exc.value.status_code == HTTPStatus.FORBIDDEN
        assert exc.value.detail == 'SCOPE_FORBIDDEN'

    async def test_no_role_forbidden(self, session):
        user = await make_user(session)
        req = make_request(active_org=None)

        with pytest.raises(HTTPException) as exc:
            await require_admin(req, session, user)
        assert exc.value.detail == 'SCOPE_FORBIDDEN'

    async def test_admin_match_is_case_insensitive(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'ADMIN', org='11gt')
        req = make_request(active_org='11gt')

        result = await require_admin(req, session, user)

        assert result is user


# --------------------------------------------------------------------------- #
# require_system_admin (admin de SISTEMA: org ativa None + vínculo None)
# --------------------------------------------------------------------------- #
class TestRequireSystemAdmin:
    async def test_success_with_system_admin(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'admin', org=None)
        req = make_request(active_org=None)

        result = await require_system_admin(req, session, user)

        assert result is user

    async def test_active_org_set_forbidden(self, session):
        """Mesmo admin de sistema perde poder ao entrar numa unidade."""
        user = await make_user(session)
        await bind_role(session, user, 'admin', org=None)
        req = make_request(active_org='11gt')

        with pytest.raises(HTTPException) as exc:
            await require_system_admin(req, session, user)
        assert exc.value.detail == 'SCOPE_FORBIDDEN'

    async def test_org_scoped_admin_forbidden(self, session):
        """Admin de unidade não é admin de sistema (vínculo não é NULL)."""
        user = await make_user(session)
        await bind_role(session, user, 'admin', org='11gt')
        req = make_request(active_org=None)

        with pytest.raises(HTTPException) as exc:
            await require_system_admin(req, session, user)
        assert exc.value.detail == 'SCOPE_FORBIDDEN'

    async def test_non_admin_forbidden(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'user', org=None)
        req = make_request(active_org=None)

        with pytest.raises(HTTPException) as exc:
            await require_system_admin(req, session, user)
        assert exc.value.detail == 'SCOPE_FORBIDDEN'

    async def test_no_role_forbidden(self, session):
        user = await make_user(session)
        req = make_request(active_org=None)

        with pytest.raises(HTTPException) as exc:
            await require_system_admin(req, session, user)
        assert exc.value.detail == 'SCOPE_FORBIDDEN'


# --------------------------------------------------------------------------- #
# AdminScope / get_admin_scope
# --------------------------------------------------------------------------- #
class TestAdminScope:
    def test_is_system_true_when_org_none(self):
        scope = AdminScope(user=object(), active_org=None)
        assert scope.is_system is True

    def test_is_system_false_when_org_present(self):
        scope = AdminScope(user=object(), active_org='11gt')
        assert scope.is_system is False

    async def test_get_admin_scope_system(self, session):
        user = await make_user(session)
        req = make_request(active_org=None)

        scope = await get_admin_scope(req, user)

        assert scope.user is user
        assert scope.is_system is True

    async def test_get_admin_scope_org(self, session):
        user = await make_user(session)
        req = make_request(active_org='11gt')

        scope = await get_admin_scope(req, user)

        assert scope.active_org == '11gt'
        assert scope.is_system is False


# --------------------------------------------------------------------------- #
# get_active_org / require_active_org
# --------------------------------------------------------------------------- #
class TestActiveOrgDeps:
    async def test_get_active_org_returns_value(self):
        assert await get_active_org(make_request(active_org='11gt')) == '11gt'

    async def test_get_active_org_none_when_absent(self):
        assert await get_active_org(make_request()) is None

    async def test_require_active_org_returns_value(self):
        assert await require_active_org('11gt') == '11gt'

    async def test_require_active_org_none_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            await require_active_org(None)
        assert exc.value.status_code == HTTPStatus.BAD_REQUEST


# --------------------------------------------------------------------------- #
# has_permission (checagem sistema/fallback, sem org ativa)
# --------------------------------------------------------------------------- #
class TestHasPermission:
    async def test_true_with_grant(self, session):
        user = await make_user(session)
        await grant(
            session, 'editor', 'docs', 'edit', org=None, user=user
        )
        assert await has_permission(user, session, 'docs', 'edit') is True

    async def test_false_without_grant(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'user', org=None)
        assert await has_permission(user, session, 'docs', 'edit') is False

    async def test_false_when_no_role(self, session):
        user = await make_user(session)
        assert await has_permission(user, session, 'docs', 'edit') is False

    async def test_false_when_roles_falsy(self, session, monkeypatch):
        """Guard defensivo: se `get_user_roles` devolver falsy, nega.

        Hoje `get_user_roles` sempre retorna dict populado (truthy), então
        este ramo é inalcançável com dados reais; o teste documenta a
        null-safety caso o contrato mude.
        """
        user = await make_user(session)

        async def _none(*args, **kwargs):
            return None

        monkeypatch.setattr(
            'fcontrol_api.security.get_user_roles', _none
        )
        assert await has_permission(user, session, 'docs', 'edit') is False


# --------------------------------------------------------------------------- #
# has_org_permission (escopado à org ativa; admin tem bypass)
# --------------------------------------------------------------------------- #
class TestHasOrgPermission:
    async def test_admin_bypass(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'admin', org='11gt')
        # admin passa mesmo para resource/action que não existe
        ok = await has_org_permission(
            user, session, '11gt', 'qualquer', 'coisa'
        )
        assert ok is True

    async def test_grant_in_active_org_true(self, session):
        user = await make_user(session)
        await grant(session, 'ops', 'om', 'update', org='11gt', user=user)
        ok = await has_org_permission(user, session, '11gt', 'om', 'update')
        assert ok is True

    async def test_without_grant_false(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'ops', org='11gt')
        ok = await has_org_permission(user, session, '11gt', 'om', 'update')
        assert ok is False

    async def test_admin_of_other_org_no_bypass(self, session):
        """Admin de '1gt' NÃO ganha bypass com org ativa '11gt'."""
        user = await make_user(session)
        await bind_role(session, user, 'admin', org='1gt')
        ok = await has_org_permission(
            user, session, '11gt', 'om', 'update'
        )
        assert ok is False

    async def test_grant_in_other_org_isolated(self, session):
        """Grant concedido em '1gt' não autoriza ação com ativa '11gt'."""
        user = await make_user(session)
        await grant(session, 'ops', 'om', 'update', org='1gt', user=user)
        ok = await has_org_permission(user, session, '11gt', 'om', 'update')
        assert ok is False


# --------------------------------------------------------------------------- #
# permission_checker (dependency factory; admin bypass + grant por org)
# --------------------------------------------------------------------------- #
class TestPermissionChecker:
    async def test_admin_bypass_returns_user(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'admin', org='11gt')
        checker = permission_checker('om', 'delete')

        result = await checker(session, '11gt', user)

        assert result is user

    async def test_admin_bypass_system_context(self, session):
        """Admin de sistema (org None) tem bypass no contexto sem org."""
        user = await make_user(session)
        await bind_role(session, user, 'admin', org=None)
        checker = permission_checker('om', 'delete')

        result = await checker(session, None, user)

        assert result is user

    async def test_grant_allows(self, session):
        user = await make_user(session)
        await grant(session, 'ops', 'om', 'update', org='11gt', user=user)
        checker = permission_checker('om', 'update')

        result = await checker(session, '11gt', user)

        assert result is user

    async def test_no_role_forbidden(self, session):
        """Usuário sem nenhum vínculo é barrado (perms vazias)."""
        user = await make_user(session)
        checker = permission_checker('om', 'update')

        with pytest.raises(HTTPException) as exc:
            await checker(session, '11gt', user)
        assert exc.value.status_code == HTTPStatus.FORBIDDEN

    async def test_without_grant_forbidden(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'ops', org='11gt')
        checker = permission_checker('om', 'update')

        with pytest.raises(HTTPException) as exc:
            await checker(session, '11gt', user)
        assert exc.value.status_code == HTTPStatus.FORBIDDEN
        assert exc.value.detail == 'Permissão negada: om.update'

    async def test_admin_of_other_org_forbidden(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'admin', org='1gt')
        checker = permission_checker('om', 'update')

        with pytest.raises(HTTPException) as exc:
            await checker(session, '11gt', user)
        assert exc.value.status_code == HTTPStatus.FORBIDDEN

    async def test_grant_of_other_org_forbidden(self, session):
        user = await make_user(session)
        await grant(session, 'ops', 'om', 'update', org='1gt', user=user)
        checker = permission_checker('om', 'update')

        with pytest.raises(HTTPException) as exc:
            await checker(session, '11gt', user)
        assert exc.value.status_code == HTTPStatus.FORBIDDEN

    async def test_denied_records_audit_log(self, session):
        """Acesso negado deixa trilha de auditoria (access_denied)."""
        user = await make_user(session)
        await bind_role(session, user, 'ops', org='11gt')
        checker = permission_checker('om', 'update')

        with pytest.raises(HTTPException):
            await checker(session, '11gt', user)

        await session.flush()
        log = await session.scalar(
            select(UserActionLog).where(
                UserActionLog.user_id == user.id,
                UserActionLog.action == 'access_denied',
                UserActionLog.resource == 'om',
            )
        )
        assert log is not None


# --------------------------------------------------------------------------- #
# ensure_permission_or_owner (dono OU permissão)
# --------------------------------------------------------------------------- #
class TestEnsurePermissionOrOwner:
    async def test_owner_allowed_without_permission(self, session):
        user = await make_user(session)
        # dono do próprio recurso: não exige grant nenhum
        await ensure_permission_or_owner(
            user, session, 'users', 'update', owner_id=user.id
        )

    async def test_non_owner_with_permission_allowed(self, session):
        user = await make_user(session)
        await grant(
            session, 'editor', 'users', 'update', org=None, user=user
        )
        await ensure_permission_or_owner(
            user, session, 'users', 'update', owner_id=user.id + 1000
        )

    async def test_non_owner_without_permission_forbidden(self, session):
        user = await make_user(session)
        await bind_role(session, user, 'user', org=None)

        with pytest.raises(HTTPException) as exc:
            await ensure_permission_or_owner(
                user, session, 'users', 'update', owner_id=user.id + 1000
            )
        assert exc.value.status_code == HTTPStatus.FORBIDDEN
