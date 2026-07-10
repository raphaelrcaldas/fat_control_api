from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.users import UserPublic


class CartaoSaudeBase(BaseModel):
    prontuario: str | None = Field(default=None, max_length=20)
    cemal: date | None = None
    tovn: date | None = None
    imae: date | None = None

    model_config = ConfigDict(from_attributes=True)


class CartaoSaudeCreate(CartaoSaudeBase):
    user_id: int


class CartaoSaudeUpdate(CartaoSaudeBase):
    # Mesmos campos opcionais do base; o PUT usa exclude_unset no handler.
    pass


class CartaoSaudePublic(CartaoSaudeBase):
    id: int
    user_id: int


class CartaoSaudeWithUser(CartaoSaudePublic):
    user: UserPublic


class UserCartaoSaude(BaseModel):
    user: UserPublic
    cartao: CartaoSaudePublic | None = None
    tripulante: bool = False
    cemal_tem_ata: bool | None = None
    total_atas: int = 0

    model_config = ConfigDict(from_attributes=True)


class OrfaoAeromedicaPublic(BaseModel):
    """Militar inativo com documentos aeromédicos (cartão e/ou atas)."""

    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None = None
    tem_cartao: bool
    total_atas: int
    atas_size: int


class OrfaosAeromedicaResumo(BaseModel):
    total_militares: int
    total_cartoes: int
    total_atas: int
    atas_size: int
    itens: list[OrfaoAeromedicaPublic]


class OrfaosAeromedicaDelete(BaseModel):
    user_ids: list[int] = Field(min_length=1)


class OrfaosAeromedicaDeleteResponse(BaseModel):
    cartoes: int
    atas: int
