"""Saneamento global de inputs de texto livre.

Espaço compartilhado de toda a API: normaliza unicode (NFC), remove
caracteres de controle/invisíveis e apara as pontas. O frontend espelha
isso por UX (`client/utils/sanitize.ts`), mas a API é a guarda final —
qualquer cliente (scripts, Postman) passa por aqui.

Uso em schemas Pydantic via os tipos `TextoLivre` (uma linha: descrições,
números de documento) e `TextoMultilinha` (com quebras de linha:
observações em textarea). As funções `sanitizar_linha`/`sanitizar_bloco`
também podem ser chamadas diretamente fora de schemas.
"""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator


def _limpar(texto: str, *, multilinha: bool) -> str:
    """Normaliza (NFC), remove caracteres de controle/formatação e apara.

    Em modo multilinha, normaliza quebras de linha para `\\n` e preserva
    `\\n`/`\\t`; caso contrário remove qualquer caractere de controle.
    """
    texto = unicodedata.normalize('NFC', texto)
    if multilinha:
        texto = texto.replace('\r\n', '\n').replace('\r', '\n')
    permitidos = {'\n', '\t'} if multilinha else set()
    texto = ''.join(
        ch
        for ch in texto
        if ch in permitidos or unicodedata.category(ch)[0] != 'C'
    )
    return texto.strip()


def sanitizar_linha(v: str) -> str:
    """Saneia texto de uma linha (remove todos os caracteres de controle)."""
    return _limpar(v, multilinha=False)


def sanitizar_bloco(v: str) -> str:
    """Saneia texto multilinha (preserva `\\n`/`\\t`)."""
    return _limpar(v, multilinha=True)


TextoLivre = Annotated[str, AfterValidator(sanitizar_linha)]
TextoMultilinha = Annotated[str, AfterValidator(sanitizar_bloco)]
