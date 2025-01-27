from pydantic import BaseModel, ConfigDict


class PostoGradSchema(BaseModel):
    id: int
    ant: int
    short: str
    mid: str
    long: str
    soldo: float
    circulo: str
    model_config = ConfigDict(from_attributes=True)
