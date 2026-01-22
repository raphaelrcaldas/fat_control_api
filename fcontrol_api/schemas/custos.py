"""Schemas para inputs de cálculo de custos de missões."""

from datetime import date

from pydantic import BaseModel, Field

from fcontrol_api.enums.posto_grad import PostoGradEnum


class CustoPernoiteInput(BaseModel):
    """
    Schema de input para cálculo de custo de pernoite.

    Usado pela função calcular_custos_frag_mis para ter type hints adequados.
    """

    id: int = Field(..., description='ID do pernoite no banco de dados')
    data_ini: date = Field(..., description='Data inicial do pernoite')
    data_fim: date = Field(..., description='Data final do pernoite')
    meia_diaria: bool = Field(
        ..., description='Se o último dia tem meia diária'
    )
    acrec_desloc: bool = Field(
        ..., description='Se há acréscimo de deslocamento (R$ 95)'
    )
    cidade_codigo: int = Field(
        ..., description='Código da cidade do pernoite', gt=0
    )

    class Config:
        frozen = True  # Imutável após criação


class CustoUserFragInput(BaseModel):
    """
    Schema de input para cálculo de custo de usuário na missão.

    Usado pela função calcular_custos_frag_mis para ter type hints adequados.
    """

    p_g: PostoGradEnum = Field(
        ...,
        description='Posto/graduação (short)',
    )
    sit: str = Field(
        ...,
        description="Situação do usuário: 'c' (comiss) ou 'g' (grat rep)",
        pattern='^[cgd]$',
    )

    class Config:
        frozen = True  # Imutável após criação


class CustoFragMisInput(BaseModel):
    """
    Schema de input para cálculo de custo de missão.

    Usado pela função calcular_custos_frag_mis para ter type hints adequados.
    """

    acrec_desloc: bool = Field(
        ...,
        description='Se a missão tem acréscimo de deslocamento global (R$ 95)',
    )

    class Config:
        frozen = True  # Imutável após criação
