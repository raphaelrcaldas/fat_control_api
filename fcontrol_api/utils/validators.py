"""Validadores de dados."""


def calcular_dv_saram(numero_base: str) -> int:
    """
    Calcula o dígito verificador (DV) do SARAM
    usando módulo 11 com pesos de 2 a 7.

    Args:
        numero_base: String com os dígitos base do SARAM (sem o DV)

    Returns:
        Dígito verificador calculado (0-9)
    """
    pesos = [2, 3, 4, 5, 6, 7]
    soma = 0

    for i, digito in enumerate(reversed(numero_base)):
        peso = pesos[i % len(pesos)]
        soma += int(digito) * peso

    resto = soma % 11
    dv = 11 - resto

    if dv == 10 or dv == 11:
        dv = 0

    return dv


def validar_saram(saram: str | int) -> bool:
    """
    Valida um SARAM completo (com DV).
    Aceita formatos: XXXXXX-D, XXXXXXD ou int.

    Args:
        saram: SARAM a ser validado (string ou int)

    Returns:
        True se o SARAM é válido, False caso contrário
    """
    # Converte para string e remove hífen, se houver
    saram_str = str(saram).replace("-", "").strip()

    if not saram_str.isdigit() or len(saram_str) < 2:
        return False

    numero_base = saram_str[:-1]
    dv_informado = int(saram_str[-1])

    dv_calculado = calcular_dv_saram(numero_base)

    return dv_informado == dv_calculado


def validar_cpf(cpf: str) -> bool:
    """
    Valida um CPF brasileiro.
    Aceita formatos: XXX.XXX.XXX-XX ou XXXXXXXXXXX.

    Args:
        cpf: CPF a ser validado (string)

    Returns:
        True se o CPF é válido, False caso contrário
    """
    # Remove caracteres não numéricos
    cpf_numeros = ''.join(c for c in cpf if c.isdigit())

    # CPF deve ter 11 dígitos
    if len(cpf_numeros) != 11:
        return False

    # Rejeita CPFs com todos os dígitos iguais (ex: 111.111.111-11)
    if len(set(cpf_numeros)) == 1:
        return False

    # Calcula o primeiro dígito verificador
    soma = 0
    for i in range(9):
        soma += int(cpf_numeros[i]) * (10 - i)
    resto = soma % 11
    dv1 = 0 if resto < 2 else 11 - resto

    if int(cpf_numeros[9]) != dv1:
        return False

    # Calcula o segundo dígito verificador
    soma = 0
    for i in range(10):
        soma += int(cpf_numeros[i]) * (11 - i)
    resto = soma % 11
    dv2 = 0 if resto < 2 else 11 - resto

    return int(cpf_numeros[10]) == dv2
