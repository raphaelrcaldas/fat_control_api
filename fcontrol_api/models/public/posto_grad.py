from sqlalchemy import Identity
from sqlalchemy.orm import Mapped, mapped_column

from .. import Base


class PostoGrad(Base):
    __tablename__ = 'posto_grad'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    ant: Mapped[int] = mapped_column(nullable=False)
    short: Mapped[str] = mapped_column(nullable=False)
    mid: Mapped[str] = mapped_column(nullable=False)
    long: Mapped[str] = mapped_column(nullable=False)
    soldo: Mapped[float] = mapped_column(nullable=False)
    circulo: Mapped[str] = mapped_column(nullable=False)
