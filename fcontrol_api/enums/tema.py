from enum import Enum


class TemaEnum(str, Enum):
    """Temas de cor de marca por organização (lista fechada e curada).

    Cada valor mapeia para uma escala Tailwind completa (50-900) no
    frontend (client/src/app/global.css, blocos `[data-org-theme]`).
    Contrato rigido: o backend valida contra esta lista; o client
    espelha os mesmos identificadores.
    """

    RED = 'red'
    BLUE = 'blue'
    EMERALD = 'emerald'
    INDIGO = 'indigo'
    AMBER = 'amber'
    TEAL = 'teal'
    ROSE = 'rose'
    VIOLET = 'violet'
    SLATE = 'slate'
