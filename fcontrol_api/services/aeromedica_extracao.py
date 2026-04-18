import re
from datetime import date, datetime
from io import BytesIO


def _parse_date(text: str) -> date | None:
    cleaned = text.strip().rstrip('.')
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def extrair_dados_ata_bytes(conteudo: bytes) -> dict:
    # Lazy import: pdfplumber custa ~300ms no cold start e só
    # é usado quando uma ata é efetivamente processada.
    import pdfplumber  # noqa: PLC0415

    resultado = {
        'nome_completo': None,
        'letra_finalidade': None,
        'data_realizacao': None,
        'validade_inspsau': None,
    }

    texto_completo = ''
    with pdfplumber.open(BytesIO(conteudo)) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if texto:
                texto_completo += texto + '\n'

    if not texto_completo:
        return resultado

    # Nome completo — busca a linha com "NOME :"
    linhas = texto_completo.splitlines()
    for i, linha in enumerate(linhas):
        if 'NOME' in linha and ':' in linha:
            nome = linha.split(':', 1)[1].strip()
            if nome:
                resultado['nome_completo'] = nome
            elif i > 0:
                # Nome na linha anterior (ex: "JULIO...\nNOME :")
                resultado['nome_completo'] = linhas[i - 1].strip()
            break

    # Letra de finalidade
    # Formato real: Letra " H " ou Letra "H" ou Letra ¨H¨
    match_letra = re.search(
        r'[Ll]etra\s*["\u201c\u00a8"\s]*([A-Z])\s*["\u201d\u00a8"\s]*',
        texto_completo,
    )
    if match_letra:
        resultado['letra_finalidade'] = match_letra.group(1)

    # Validade da INSPSAU / INSPEÇÃO
    match_validade = re.search(
        r'VALIDADE\s*(?:DA\s*)?(?:INSPSAU|INSPE[CÇ][AÃ]O)'
        r'\s*[:\-]\s*(\d{2}/\d{2}/\d{4})',
        texto_completo,
        re.IGNORECASE,
    )
    if match_validade:
        resultado['validade_inspsau'] = _parse_date(match_validade.group(1))

    # Data de realização
    # Formato real: "SALA DE SESSÕES ... em 11/03/2026"
    match_realizacao = re.search(
        r'(?:SALA\s+DE\s+SESS[OÕ]ES|JUNTA\s+DE\s+SA[UÚ]DE)'
        r'.*?em\s+(\d{2}/\d{2}/\d{4})',
        texto_completo,
        re.IGNORECASE,
    )
    if not match_realizacao:
        # Fallback: "data da realização" ou "realizada em"
        match_realizacao = re.search(
            r'(?:data\s*(?:da\s*)?realiza[cç][aã]o'
            r'|realizada\s*em)'
            r'\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})',
            texto_completo,
            re.IGNORECASE,
        )
    if match_realizacao:
        resultado['data_realizacao'] = _parse_date(match_realizacao.group(1))

    return resultado
