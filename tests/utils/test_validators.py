"""Testes para validadores."""

import pytest

from fcontrol_api.utils.validators import (
    calcular_dv_saram,
    validar_cpf,
    validar_saram,
)


class TestCalcularDvSaram:
    """Testes para calcular_dv_saram."""

    def test_calcula_dv_correto_exemplo_1(self):
        """Testa cálculo de DV para um SARAM de exemplo."""
        # SARAM: 1234560 -> base: 123456, DV: 0
        # Cálculo: 6*2 + 5*3 + 4*4 + 3*5 + 2*6 + 1*7 = 77
        # 77 % 11 = 0, DV = 11 - 0 = 11 -> 0
        assert calcular_dv_saram('123456') == 0

    def test_calcula_dv_correto_exemplo_2(self):
        """Testa cálculo de DV para outro SARAM."""
        # SARAM: 9876545 -> base: 987654, DV: 5
        assert calcular_dv_saram('987654') == 5

    def test_calcula_dv_com_resultado_10_vira_0(self):
        """Testa que DV = 10 é convertido para 0."""
        # Encontrar um número que resulte em DV = 10
        # 100000 -> soma = 0*2 + 0*3 + 0*4 + 0*5 + 0*6 + 1*7 = 7
        # resto = 7, DV = 11 - 7 = 4
        # Vamos usar: 100001
        # soma = 1*2 + 0*3 + 0*4 + 0*5 + 0*6 + 1*7 = 9
        # resto = 9, DV = 11 - 9 = 2
        # Vamos usar: 999999
        # soma = 9*2 + 9*3 + 9*4 + 9*5 + 9*6 + 9*7 = 189
        # resto = 189 % 11 = 2, DV = 11 - 2 = 9
        # Vamos usar: 100000
        # Para ter resto = 1, precisamos soma % 11 = 1
        # DV = 11 - 1 = 10 -> 0
        # Testando 545454: 4*2 + 5*3 + 4*4 + 5*5 + 4*6 + 5*7 = 8+15+16+25+24+35 = 123
        # 123 % 11 = 2, DV = 11 - 2 = 9
        # Testando 909090: 0*2 + 9*3 + 0*4 + 9*5 + 0*6 + 9*7 = 27+45+63 = 135
        # 135 % 11 = 3, DV = 11 - 3 = 8
        # Testando 100000: 0*2 + 0*3 + 0*4 + 0*5 + 0*6 + 1*7 = 7
        # 7 % 11 = 7, DV = 11 - 7 = 4
        # Para ter DV = 10, precisamos resto = 1
        # Testando 272727: 7*2 + 2*3 + 7*4 + 2*5 + 7*6 + 2*7 = 14+6+28+10+42+14 = 114
        # 114 % 11 = 4, DV = 11 - 4 = 7
        # Testando 181818: 8*2 + 1*3 + 8*4 + 1*5 + 8*6 + 1*7 = 16+3+32+5+48+7 = 111
        # 111 % 11 = 1, DV = 11 - 1 = 10 -> 0
        dv = calcular_dv_saram('181818')
        assert dv == 0

    def test_calcula_dv_com_resultado_11_vira_0(self):
        """Testa que DV = 11 é convertido para 0."""
        # Para ter DV = 11, precisamos resto = 0
        # Testando 272727: soma = 114 (já calculado), 114 % 11 = 4
        # Testando 363636: 6*2 + 3*3 + 6*4 + 3*5 + 6*6 + 3*7 = 12+9+24+15+36+21 = 117
        # 117 % 11 = 7, DV = 11 - 7 = 4
        # Testando 454545: 5*2 + 4*3 + 5*4 + 4*5 + 5*6 + 4*7 = 10+12+20+20+30+28 = 120
        # 120 % 11 = 10, DV = 11 - 10 = 1
        # Testando 545454: soma = 123 (já calculado), 123 % 11 = 2
        # Testando 636363: 3*2 + 6*3 + 3*4 + 6*5 + 3*6 + 6*7 = 6+18+12+30+18+42 = 126
        # 126 % 11 = 5, DV = 11 - 5 = 6
        # Testando 727272: 2*2 + 7*3 + 2*4 + 7*5 + 2*6 + 7*7 = 4+21+8+35+12+49 = 129
        # 129 % 11 = 8, DV = 11 - 8 = 3
        # Testando 818181: 1*2 + 8*3 + 1*4 + 8*5 + 1*6 + 8*7 = 2+24+4+40+6+56 = 132
        # 132 % 11 = 0, DV = 11 - 0 = 11 -> 0
        dv = calcular_dv_saram('818181')
        assert dv == 0


class TestValidarSaram:
    """Testes para validar_saram."""

    def test_valida_saram_correto_int(self):
        """Testa validação de SARAM válido como int."""
        assert validar_saram(1234560) is True

    def test_valida_saram_correto_string(self):
        """Testa validação de SARAM válido como string."""
        assert validar_saram('1234560') is True

    def test_valida_saram_correto_com_hifen(self):
        """Testa validação de SARAM válido com hífen."""
        assert validar_saram('123456-0') is True

    def test_valida_saram_incorreto(self):
        """Testa rejeição de SARAM com DV incorreto."""
        # SARAM com DV errado
        assert validar_saram(1234568) is False

    def test_valida_saram_exemplo_real_1(self):
        """Testa validação de SARAM real."""
        # 9876545 tem DV correto (5)
        assert validar_saram(9876545) is True

    def test_valida_saram_exemplo_real_2(self):
        """Testa rejeição de SARAM real com DV errado."""
        # 9876543 tem DV errado (deveria ser 5)
        assert validar_saram(9876543) is False

    def test_valida_saram_com_dv_zero_por_resultado_10(self):
        """Testa SARAM onde DV = 10 vira 0."""
        # 1818180 (base 181818, DV calculado = 10 -> 0)
        assert validar_saram(1818180) is True

    def test_valida_saram_com_dv_zero_por_resultado_11(self):
        """Testa SARAM onde DV = 11 vira 0."""
        # 8181810 (base 818181, DV calculado = 11 -> 0)
        assert validar_saram(8181810) is True

    def test_rejeita_saram_vazio(self):
        """Testa rejeição de string vazia."""
        assert validar_saram('') is False

    def test_rejeita_saram_muito_curto(self):
        """Testa rejeição de SARAM muito curto."""
        assert validar_saram('1') is False

    def test_rejeita_saram_nao_numerico(self):
        """Testa rejeição de SARAM com caracteres não numéricos."""
        assert validar_saram('123abc7') is False

    def test_rejeita_saram_com_espacos(self):
        """Testa rejeição de SARAM com espaços no meio."""
        assert validar_saram('123 456 7') is False

    def test_aceita_saram_com_espacos_nas_pontas(self):
        """Testa que espaços nas pontas são removidos."""
        assert validar_saram('  1234560  ') is True


class TestValidarCpf:
    """Testes para validar_cpf."""

    def test_valida_cpf_correto_sem_formatacao(self):
        """Testa validação de CPF válido sem formatação."""
        assert validar_cpf('52998224725') is True

    def test_valida_cpf_correto_com_formatacao(self):
        """Testa validação de CPF válido com formatação."""
        assert validar_cpf('529.982.247-25') is True

    def test_rejeita_cpf_com_dv_incorreto(self):
        """Testa rejeição de CPF com dígito verificador incorreto."""
        assert validar_cpf('52998224700') is False

    def test_rejeita_cpf_com_digitos_iguais(self):
        """Testa rejeição de CPFs com todos os dígitos iguais."""
        assert validar_cpf('11111111111') is False
        assert validar_cpf('00000000000') is False
        assert validar_cpf('99999999999') is False

    def test_rejeita_cpf_muito_curto(self):
        """Testa rejeição de CPF com menos de 11 dígitos."""
        assert validar_cpf('1234567890') is False

    def test_rejeita_cpf_muito_longo(self):
        """Testa rejeição de CPF com mais de 11 dígitos."""
        assert validar_cpf('123456789012') is False

    def test_rejeita_cpf_vazio(self):
        """Testa rejeição de string vazia."""
        assert validar_cpf('') is False

    def test_valida_cpf_conhecido_1(self):
        """Testa CPF válido conhecido."""
        # CPF de teste comumente usado
        assert validar_cpf('453.178.287-91') is True

    def test_valida_cpf_conhecido_2(self):
        """Testa outro CPF válido conhecido."""
        assert validar_cpf('111.444.777-35') is True

    def test_rejeita_cpf_com_primeiro_dv_errado(self):
        """Testa rejeição quando primeiro dígito verificador está errado."""
        # 529.982.247-25 é válido, 529.982.247-35 tem primeiro DV errado
        assert validar_cpf('529.982.247-35') is False

    def test_rejeita_cpf_com_segundo_dv_errado(self):
        """Testa rejeição quando segundo dígito verificador está errado."""
        # 529.982.247-25 é válido, 529.982.247-26 tem segundo DV errado
        assert validar_cpf('529.982.247-26') is False
