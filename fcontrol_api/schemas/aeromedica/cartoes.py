from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.users import UserPublic


class CartaoSaudeBase(BaseModel):
    prontuario: str | None = None
    cemal: date | None = None
    ag_cemal: date | None = None
    tovn: date | None = None
    imae: date | None = None

    model_config = ConfigDict(from_attributes=True)


class CartaoSaudeCreate(CartaoSaudeBase):
    user_id: int


class CartaoSaudeUpdate(CartaoSaudeBase):
    prontuario: str | None = None
    cemal: Optional[date] = None
    ag_cemal: Optional[date] = None
    tovn: Optional[date] = None
    imae: Optional[date] = None


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
