"""
Testes para validacoes dos schemas de usuarios.

Testa as validacoes de:
- SARAM (digito verificador e apenas digitos)
- CPF (digito verificador)
- ID FAB (apenas digitos)
- Email FAB (termina com @fab.mil.br)
- Senha (forca da senha)
"""

import pytest
from pydantic import ValidationError

from fcontrol_api.schemas.users import PwdSchema, UserSchema, UserUpdate

# Dados base validos para criacao de usuarios
VALID_USER_DATA = {
    'p_g': '2s',
    'esp': 'inf',
    'nome_guerra': 'fulano',
    'nome_completo': 'Fulano da Silva',
    'id_fab': '123456',
    'saram': '9876545',  # SARAM valido com DV correto
    'cpf': '52998224725',  # CPF valido
    'ult_promo': '2020-01-15',
    'nasc': '1990-05-20',
    'email_pess': 'fulano@email.com',
    'email_fab': 'fulano@fab.mil.br',
    'active': True,
    'unidade': 'TEST',
    'ant_rel': 100,
}


class TestUserSchemaSaramValidation:
    """Testes para validacao de SARAM."""

    def test_saram_valido_aceito(self):
        """SARAM com DV correto deve ser aceito."""
        data = {**VALID_USER_DATA, 'saram': '9876545'}
        user = UserSchema(**data)
        assert user.saram == '9876545'

    def test_saram_dv_incorreto_rejeitado(self):
        """SARAM com DV incorreto deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'saram': '9876543'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'saram' in str(exc_info.value).lower()

    def test_saram_com_letras_rejeitado(self):
        """SARAM com letras deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'saram': '987654a'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'saram' in str(exc_info.value).lower()

    def test_saram_com_caracteres_especiais_rejeitado(self):
        """SARAM com caracteres especiais deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'saram': '98765-5'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'saram' in str(exc_info.value).lower()

    def test_saram_com_espacos_rejeitado(self):
        """SARAM com espacos deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'saram': '987 545'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'saram' in str(exc_info.value).lower()

    def test_saram_muito_curto_rejeitado(self):
        """SARAM com menos de 7 digitos deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'saram': '12345'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'saram' in str(exc_info.value).lower()

    def test_saram_muito_longo_rejeitado(self):
        """SARAM com mais de 7 digitos deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'saram': '12345678'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'saram' in str(exc_info.value).lower()


class TestUserSchemaCpfValidation:
    """Testes para validacao de CPF."""

    def test_cpf_valido_aceito(self):
        """CPF valido deve ser aceito."""
        data = {**VALID_USER_DATA, 'cpf': '52998224725'}
        user = UserSchema(**data)
        assert user.cpf == '52998224725'

    def test_cpf_invalido_rejeitado(self):
        """CPF com DVs incorretos deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'cpf': '52998224720'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'cpf' in str(exc_info.value).lower()

    def test_cpf_digitos_iguais_rejeitado(self):
        """CPF com todos os digitos iguais deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'cpf': '11111111111'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'cpf' in str(exc_info.value).lower()

    def test_cpf_muito_curto_rejeitado(self):
        """CPF com menos de 11 digitos deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'cpf': '1234567890'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'cpf' in str(exc_info.value).lower()

    def test_cpf_vazio_aceito(self):
        """CPF vazio deve ser aceito (campo opcional)."""
        data = {**VALID_USER_DATA, 'cpf': ''}
        user = UserSchema(**data)
        assert not user.cpf


class TestUserSchemaIdFabValidation:
    """Testes para validacao de ID FAB."""

    def test_id_fab_valido_aceito(self):
        """ID FAB com 6 digitos deve ser aceito."""
        data = {**VALID_USER_DATA, 'id_fab': '123456'}
        user = UserSchema(**data)
        assert user.id_fab == '123456'

    def test_id_fab_com_letras_rejeitado(self):
        """ID FAB com letras deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'id_fab': '12345a'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'id' in str(exc_info.value).lower()

    def test_id_fab_muito_curto_rejeitado(self):
        """ID FAB com menos de 6 digitos deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'id_fab': '12345'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'id_fab' in str(exc_info.value).lower()

    def test_id_fab_muito_longo_rejeitado(self):
        """ID FAB com mais de 6 digitos deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'id_fab': '1234567'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'id_fab' in str(exc_info.value).lower()

    def test_id_fab_none_aceito(self):
        """ID FAB None deve ser aceito (campo opcional)."""
        data = {**VALID_USER_DATA, 'id_fab': None}
        user = UserSchema(**data)
        assert user.id_fab is None


class TestUserSchemaEmailFabValidation:
    """Testes para validacao de Email FAB (Zimbra)."""

    def test_email_fab_valido_aceito(self):
        """Email terminando com @fab.mil.br deve ser aceito."""
        data = {**VALID_USER_DATA, 'email_fab': 'fulano@fab.mil.br'}
        user = UserSchema(**data)
        assert user.email_fab == 'fulano@fab.mil.br'

    def test_email_fab_dominio_errado_rejeitado(self):
        """Email com dominio diferente de @fab.mil.br deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'email_fab': 'fulano@gmail.com'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        error_msg = str(exc_info.value).lower()
        assert 'email' in error_msg or 'fab.mil.br' in error_msg

    def test_email_fab_dominio_similar_rejeitado(self):
        """Email com dominio similar mas incorreto deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'email_fab': 'fulano@fab.mil.com'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        error_msg = str(exc_info.value).lower()
        assert 'email' in error_msg or 'fab.mil.br' in error_msg

    def test_email_fab_sem_arroba_rejeitado(self):
        """Email sem @ deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'email_fab': 'fulanofab.mil.br'}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'email' in str(exc_info.value).lower()

    def test_email_fab_case_insensitive(self):
        """Validacao de dominio deve ser case-insensitive."""
        data = {**VALID_USER_DATA, 'email_fab': 'fulano@FAB.MIL.BR'}
        user = UserSchema(**data)
        # EmailStr normaliza para lowercase
        assert user.email_fab == 'fulano@fab.mil.br'

    def test_email_fab_vazio_rejeitado(self):
        """Email FAB vazio deve ser rejeitado."""
        data = {**VALID_USER_DATA, 'email_fab': ''}
        with pytest.raises(ValidationError) as exc_info:
            UserSchema(**data)
        assert 'email' in str(exc_info.value).lower()


class TestUserUpdateSaramValidation:
    """Testes para validacao de SARAM em UserUpdate."""

    def test_saram_valido_aceito(self):
        """SARAM valido deve ser aceito em update."""
        update = UserUpdate(saram='9876545')
        assert update.saram == '9876545'

    def test_saram_none_aceito(self):
        """SARAM None deve ser aceito em update (campo opcional)."""
        update = UserUpdate(saram=None)
        assert update.saram is None

    def test_saram_invalido_rejeitado(self):
        """SARAM invalido deve ser rejeitado em update."""
        with pytest.raises(ValidationError) as exc_info:
            UserUpdate(saram='9876543')
        assert 'saram' in str(exc_info.value).lower()

    def test_saram_com_letras_rejeitado(self):
        """SARAM com letras deve ser rejeitado em update."""
        with pytest.raises(ValidationError) as exc_info:
            UserUpdate(saram='987654a')
        error_msg = str(exc_info.value).lower()
        assert 'saram' in error_msg or 'dígitos' in error_msg


class TestUserUpdateCpfValidation:
    """Testes para validacao de CPF em UserUpdate."""

    def test_cpf_valido_aceito(self):
        """CPF valido deve ser aceito em update."""
        update = UserUpdate(cpf='52998224725')
        assert update.cpf == '52998224725'

    def test_cpf_none_aceito(self):
        """CPF None deve ser aceito em update (campo opcional)."""
        update = UserUpdate(cpf=None)
        assert update.cpf is None

    def test_cpf_invalido_rejeitado(self):
        """CPF invalido deve ser rejeitado em update."""
        with pytest.raises(ValidationError) as exc_info:
            UserUpdate(cpf='12345678900')
        assert 'cpf' in str(exc_info.value).lower()


class TestUserUpdateIdFabValidation:
    """Testes para validacao de ID FAB em UserUpdate."""

    def test_id_fab_valido_aceito(self):
        """ID FAB valido deve ser aceito em update."""
        update = UserUpdate(id_fab='123456')
        assert update.id_fab == '123456'

    def test_id_fab_none_aceito(self):
        """ID FAB None deve ser aceito em update (campo opcional)."""
        update = UserUpdate(id_fab=None)
        assert update.id_fab is None

    def test_id_fab_com_letras_rejeitado(self):
        """ID FAB com letras deve ser rejeitado em update."""
        with pytest.raises(ValidationError) as exc_info:
            UserUpdate(id_fab='12345a')
        assert 'id' in str(exc_info.value).lower()


class TestUserUpdateEmailFabValidation:
    """Testes para validacao de Email FAB em UserUpdate."""

    def test_email_fab_valido_aceito(self):
        """Email valido deve ser aceito em update."""
        update = UserUpdate(email_fab='fulano@fab.mil.br')
        assert update.email_fab == 'fulano@fab.mil.br'

    def test_email_fab_none_aceito(self):
        """Email None deve ser aceito em update (campo opcional)."""
        update = UserUpdate(email_fab=None)
        assert update.email_fab is None

    def test_email_fab_invalido_rejeitado(self):
        """Email com dominio errado deve ser rejeitado em update."""
        with pytest.raises(ValidationError) as exc_info:
            UserUpdate(email_fab='fulano@gmail.com')
        error_msg = str(exc_info.value).lower()
        assert 'email' in error_msg or 'fab.mil.br' in error_msg

    def test_email_fab_vazio_rejeitado(self):
        """Email FAB vazio deve ser rejeitado em update."""
        with pytest.raises(ValidationError) as exc_info:
            UserUpdate(email_fab='')
        error_msg = str(exc_info.value).lower()
        assert 'email' in error_msg or 'fab.mil.br' in error_msg


class TestPwdSchemaValidation:
    """Testes para validacao de senha (PwdSchema)."""

    def test_senha_valida_aceita(self):
        """Senha que atende todos os requisitos deve ser aceita."""
        pwd = PwdSchema(new_pwd='Senha@123')
        assert pwd.new_pwd == 'Senha@123'

    def test_senha_sem_maiuscula_rejeitada(self):
        """Senha sem letra maiuscula deve ser rejeitada."""
        with pytest.raises(ValidationError) as exc_info:
            PwdSchema(new_pwd='senha@123')
        error_msg = str(exc_info.value).lower()
        assert 'maiúscula' in error_msg or 'maiuscula' in error_msg

    def test_senha_sem_minuscula_rejeitada(self):
        """Senha sem letra minuscula deve ser rejeitada."""
        with pytest.raises(ValidationError) as exc_info:
            PwdSchema(new_pwd='SENHA@123')
        error_msg = str(exc_info.value).lower()
        assert 'minúscula' in error_msg or 'minuscula' in error_msg

    def test_senha_sem_digito_rejeitada(self):
        """Senha sem digito deve ser rejeitada."""
        with pytest.raises(ValidationError) as exc_info:
            PwdSchema(new_pwd='Senha@abc')
        error_msg = str(exc_info.value).lower()
        assert 'dígito' in error_msg or 'digito' in error_msg

    def test_senha_sem_caractere_especial_rejeitada(self):
        """Senha sem caractere especial deve ser rejeitada."""
        with pytest.raises(ValidationError) as exc_info:
            PwdSchema(new_pwd='Senha1234')
        error_msg = str(exc_info.value).lower()
        assert 'especial' in error_msg

    def test_senha_muito_curta_rejeitada(self):
        """Senha com menos de 8 caracteres deve ser rejeitada."""
        with pytest.raises(ValidationError) as exc_info:
            PwdSchema(new_pwd='Se@1')
        assert 'new_pwd' in str(exc_info.value).lower()

    def test_senha_muito_longa_rejeitada(self):
        """Senha com mais de 128 caracteres deve ser rejeitada."""
        senha_longa = 'Aa@1' + 'a' * 125  # 129 caracteres
        with pytest.raises(ValidationError) as exc_info:
            PwdSchema(new_pwd=senha_longa)
        assert 'new_pwd' in str(exc_info.value).lower()

    def test_senha_com_multiplos_erros(self):
        """Senha com multiplos erros deve listar todos os requisitos."""
        with pytest.raises(ValidationError) as exc_info:
            PwdSchema(new_pwd='senhafraca')
        error_msg = str(exc_info.value).lower()
        # Deve mencionar maiuscula, digito e caractere especial
        assert 'maiúscula' in error_msg or 'maiuscula' in error_msg
        assert 'dígito' in error_msg or 'digito' in error_msg
        assert 'especial' in error_msg

    def test_senha_com_caracteres_especiais_diversos(self):
        """Senha com diferentes caracteres especiais deve ser aceita."""
        caracteres_especiais = [
            '!',
            '@',
            '#',
            '$',
            '%',
            '^',
            '&',
            '*',
            '_',
            '-',
        ]
        for char in caracteres_especiais:
            pwd = PwdSchema(new_pwd=f'Senha{char}123')
            assert pwd.new_pwd == f'Senha{char}123'
