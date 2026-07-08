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
