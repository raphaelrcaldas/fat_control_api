from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RelatorioVooOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    anv: str
    data: date
    seq: int
    file_path: str
    file_name: str
    file_size: int
    num_paginas: int | None = None
    obs: str | None = None
    uploaded_by: int
    uploaded_by_p_g: str
    uploaded_by_nome_guerra: str
    created_at: datetime

    @classmethod
    def de(cls, relatorio, p_g, nome_guerra: str) -> 'RelatorioVooOut':
        """Monta a saída juntando o autor (posto e nome de guerra)."""
        return cls(
            id=relatorio.id,
            anv=relatorio.anv,
            data=relatorio.data,
            seq=relatorio.seq,
            file_path=relatorio.file_path,
            file_name=relatorio.file_name,
            file_size=relatorio.file_size,
            num_paginas=relatorio.num_paginas,
            obs=relatorio.obs,
            uploaded_by=relatorio.uploaded_by,
            uploaded_by_p_g=getattr(p_g, 'value', p_g),
            uploaded_by_nome_guerra=nome_guerra,
            created_at=relatorio.created_at,
        )


class RelatoriosVooPeriodoOut(BaseModel):
    itens: list[RelatorioVooOut]
    # Contagem do período inteiro por aeronave, sem o filtro `anv`: é o
    # número que os chips da frota mostram.
    contagem_por_anv: dict[str, int]


class RelatorioVooArquivoOut(BaseModel):
    url: str


class RelatorioVooUpdate(BaseModel):
    # Obrigatório (sem default) para que `PATCH {}` seja 422 em vez de
    # apagar a observação; `null` é aceito e limpa a observação.
    obs: str | None = Field(max_length=500)

    @field_validator('obs', mode='before')
    @classmethod
    def vazio_vira_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v
