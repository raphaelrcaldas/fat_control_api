from datetime import date
from typing import Annotated, Literal

from fastapi import Body
from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# TIPOS BASE
# =============================================================================

# Operacionalidade continua Literal: 'ba/op/in/al' é doutrina, igual em
# qualquer unidade. Já a FUNÇÃO virou dado (tabelas `funcoes` e
# `funcoes_uae`) — o conjunto válido depende da org, então não há Literal
# de função aqui; a checagem é feita na rota contra as funções operadas
# pela org ativa, mesmo padrão de `proj`/`tenant_projetos`.
opers = Literal['ba', 'op', 'in', 'al']


class BaseFunc(BaseModel):
    """Campos de função do tripulante (colunas de `tripulantes`)."""

    # FK para `funcoes.cod`, validada na rota contra `funcoes_uae`.
    func: str = Field(min_length=2, max_length=3)
    oper: opers
    # FK para `projetos_anvs.modelo`: o catálogo é dinâmico e o conjunto
    # válido depende da org (tenant_projetos), então a checagem é feita na
    # rota contra os projetos da org ativa, não por Literal fechado aqui.
    proj: str
    data_op: Annotated[date | None, Body()] = None
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# CATÁLOGO (tabelas `funcoes` / `funcoes_posicoes`)
# =============================================================================


class FuncaoPosicaoBase(BaseModel):
    cod: str = Field(min_length=1, max_length=2)
    nome: str = Field(min_length=1, max_length=40)
    descricao: str | None = Field(default=None, max_length=80)
    tipo: Literal['titular', 'instrutor', 'aluno'] = 'titular'
    ordem: int = Field(ge=0, le=99)


class FuncaoPosicaoOut(FuncaoPosicaoBase):
    id: int
    func_cod: str
    model_config = ConfigDict(from_attributes=True)


class FuncaoBase(BaseModel):
    nome: str = Field(min_length=1, max_length=40)
    nome_curto: str = Field(min_length=1, max_length=20)
    cor: str = Field(min_length=1, max_length=16)
    ordem: int = Field(ge=0, le=99)
    esporadica: bool = False
    active: bool = True


class FuncaoCreate(FuncaoBase):
    cod: str = Field(min_length=2, max_length=3)


class FuncaoUpdate(FuncaoBase):
    """Update total do catálogo — o código é imutável (é a PK e a FK)."""


class FuncaoOut(FuncaoBase):
    cod: str
    posicoes: list[FuncaoPosicaoOut] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class FuncaoPosicoesSet(BaseModel):
    """Conjunto completo de posições de uma função (substitui as atuais)."""

    posicoes: list[FuncaoPosicaoBase]


# =============================================================================
# ESCOPO POR UNIDADE (tabela `funcoes_uae`)
# =============================================================================


class FuncaoOrgItem(BaseModel):
    cod: str = Field(min_length=2, max_length=3)
    nome_custom: str | None = Field(default=None, max_length=40)
    ordem: int | None = Field(default=None, ge=0, le=99)


class FuncoesOrgSet(BaseModel):
    """Conjunto de funções operadas pela org (substitui o atual)."""

    funcoes: list[FuncaoOrgItem]


class FuncaoOrgOut(BaseModel):
    """Função como a org a enxerga: rótulo efetivo e ordem efetiva."""

    cod: str
    nome: str
    nome_curto: str
    cor: str
    ordem: int
    esporadica: bool
    posicoes: list[FuncaoPosicaoOut] = Field(default_factory=list)
