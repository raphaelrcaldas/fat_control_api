"""Utilitarios para manipulacao de strings."""


def escape_like(value: str) -> str:
    """Escapa caracteres especiais para ILIKE (%, _, \\)."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
