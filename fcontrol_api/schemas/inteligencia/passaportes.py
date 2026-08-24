from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from fcontrol_api.enums.local_passaporte import LocalPassaporteEnum


class PassaporteBase(BaseModel):
    passaporte: str | None = None
    data_expedicao_passaporte: date | None = None
    validade_passaporte: date | None = None
    visa: str | None = None
    data_expedicao_visa: date | None = None
    validade_visa: date | None = None
    # Coluna NOT NULL no model: sempre viaja preenchida, e o default
    # espelha o `server_default` (registro sem informação = na seção).
    local_passaporte: LocalPassaporteEnum = LocalPassaporteEnum.SECAO

    model_config = ConfigDict(from_attributes=True)


class PassaporteUpdate(PassaporteBase):
    # `use_enum_values`: valida contra a lista fechada mas guarda a string
    # crua, que é o que a coluna String(20) espera (tanto no `setattr` do
    # update quanto no construtor do create). `validate_default` é o que
    # estende isso ao payload que omite a chave — sem ele o default herdado
    # entra como membro do Enum e vai para a coluna como objeto.
    model_config = ConfigDict(
        from_attributes=True, use_enum_values=True, validate_default=True
    )

    @field_validator('passaporte', 'visa', mode='before')
    @classmethod
    def normalizar_documento(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        return v or None

    @model_validator(mode='after')
    def validar_datas(self):
        if (
            self.data_expedicao_passaporte
            and self.validade_passaporte
            and self.data_expedicao_passaporte > self.validade_passaporte
        ):
            raise ValueError(
                'Data de expedicao do passaporte nao pode ser '
                'maior que a validade'
            )
        if (
            self.data_expedicao_visa
            and self.validade_visa
            and self.data_expedicao_visa > self.validade_visa
        ):
            raise ValueError(
                'Data de expedicao do visto nao pode ser maior que a validade'
            )
        return self


class PassaportePublic(PassaporteBase):
    id: int
    user_id: int
    # URLs assinadas (efêmeras) das imagens, preenchidas nos handlers a
    # partir das keys *_file_path do ORM. As colunas cruas não são expostas.
    passaporte_url: str | None = None
    visa_url: str | None = None


class TripPassaporteOut(BaseModel):
    trip_id: int
    user_id: int
    p_g: str
    quadro: str | None
    esp: str | None
    nome_guerra: str
    nome_completo: str | None
    nasc: date | None
    saram: str | None
    telefone: str | None
    passaporte: PassaportePublic | None = None

    model_config = ConfigDict(from_attributes=True)


class PassaporteOrfaoPublic(BaseModel):
    """Militar inativo com registro de passaporte (limpeza).

    `tem_passaporte`/`tem_visa` indicam imagens ainda no bucket — a
    exclusão remove o registro inteiro e as imagens juntas.
    """

    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None
    tem_passaporte: bool
    tem_visa: bool


class PassaportesOrfaosResumo(BaseModel):
    total_registros: int
    total_imagens: int
    itens: list[PassaporteOrfaoPublic]


class PassaportesOrfaosDelete(BaseModel):
    user_ids: list[int] = Field(min_length=1)


class PassaportesOrfaosDeleteResponse(BaseModel):
    registros: int
    imagens: int
