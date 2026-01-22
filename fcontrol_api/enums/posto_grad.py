from enum import Enum


class PostoGradEnum(str, Enum):
    """Postos e graduações militares."""

    # Oficiais Generais
    TB = 'tb'  # Tenente-Brigadeiro
    MB = 'mb'  # Major-Brigadeiro
    BR = 'br'  # Brigadeiro

    # Oficiais Superiores
    CL = 'cl'  # Coronel
    TC = 'tc'  # Tenente-Coronel
    MJ = 'mj'  # Major

    # Oficiais Intermediários
    CP = 'cp'  # Capitão

    # Oficiais Subalternos
    T1 = '1t'  # Primeiro Tenente
    T2 = '2t'  # Segundo Tenente
    AS = 'as'  # Aspirante

    # Graduados
    SO = 'so'  # Suboficial
    S1 = '1s'  # Primeiro Sargento
    S2 = '2s'  # Segundo Sargento
    S3 = '3s'  # Terceiro Sargento

    # Praças
    CB = 'cb'  # Cabo
    SD1 = 's1'  # Soldado Primeira Classe
    SD2 = 's2'  # Soldado Segunda Classe
