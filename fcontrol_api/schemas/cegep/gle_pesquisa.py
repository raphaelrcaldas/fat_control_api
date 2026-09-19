"""Schemas da pesquisa de missões que passaram por localidade especial.

O propósito da pesquisa é **binário**: saber se a missão passou por uma
localidade especial. Por isso o resultado agrupa por missão, e as etapas
descem apenas como evidência resumida de onde e quando o contato ocorreu —
não é relatório de horas nem de permanência.

Pela mesma razão, **tocar em qualquer ponta conta**: decolar de uma
localidade especial e pousar nela contam igual, porque ambos provam que a
missão passou por lá.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict


class EtapaContato(BaseModel):
    """Uma etapa que tocou localidade especial — a evidência."""

    etapa_id: int
    data: date
    origem: str
    destino: str
    anv: str
    #: ICAO(s) desta etapa que são localidade especial. Pode ter os dois,
    #: quando a etapa liga duas localidades especiais.
    icaos_loc_esp: list[str]

    model_config = ConfigDict(from_attributes=True)


class LocalidadeTocada(BaseModel):
    """Localidade por onde a missão passou, com o grupo."""

    loc_esp_id: int
    cidade: str
    uf: str
    grupo: int
    icaos: list[str]


class MissaoComLocEsp(BaseModel):
    """Missão que passou por ao menos uma localidade especial."""

    missao_id: int
    titulo: str | None
    #: Intervalo das etapas que tocaram localidade especial (não da missão
    #: inteira): é o que situa o contato no tempo.
    primeira_data: date
    ultima_data: date
    #: Quantas etapas da missão tocaram localidade especial.
    total_etapas: int
    localidades: list[LocalidadeTocada]
    etapas: list[EtapaContato]


class PesquisaLocEspOut(BaseModel):
    total_missoes: int
    missoes: list[MissaoComLocEsp]
