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
