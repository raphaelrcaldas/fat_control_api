from pydantic import BaseModel, ConfigDict


class PostoGradSchema(BaseModel):
    ant: int
    short: str
    mid: str
    long: str
    circulo: str
    model_config = ConfigDict(from_attributes=True)
