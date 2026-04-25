from typing import Literal

from pydantic import BaseModel, ConfigDict

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.cegep.missoes import FragMisEmbed
from fcontrol_api.schemas.users import UserPublic


class UserFragPublic(BaseModel):
    """UserFrag para resposta pública — sem user_id e frag_id."""

    id: int
    p_g: PostoGradEnum
    sit: Literal['c', 'd', 'g']
    user: UserPublic

    model_config = ConfigDict(from_attributes=True)


class PagamentoItem(BaseModel):
    user_mis: UserFragPublic
    missao: FragMisEmbed
