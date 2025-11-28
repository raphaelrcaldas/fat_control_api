from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..public.users import User
from .base import Base


class OAuth2Client(Base):
    __tablename__ = 'oauth2_clients'

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    client_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True
    )
    client_secret: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    redirect_uri: Mapped[str] = mapped_column(String(255))
    tokens: Mapped[list['OAuth2Token']] = relationship(
        back_populates='client', init=False, default_factory=list
    )
    codes: Mapped[list['OAuth2AuthorizationCode']] = relationship(
        back_populates='client', init=False, default_factory=list
    )

    is_confidential: Mapped[bool] = mapped_column(default=False)


class OAuth2AuthorizationCode(Base):
    __tablename__ = 'oauth2_authorization_codes'

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    code: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    client_id: Mapped[int] = mapped_column(ForeignKey(OAuth2Client.id))

    code_challenge: Mapped[str] = mapped_column(String(255))

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    client: Mapped[OAuth2Client] = relationship(
        back_populates='codes', init=False
    )
    user: Mapped[User] = relationship(init=False)
    code_challenge_method: Mapped[str] = mapped_column(
        String(10), default='S256'
    )


class OAuth2Token(Base):
    __tablename__ = 'oauth2_tokens'

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    access_token: Mapped[str] = mapped_column(
        String(255), unique=True, index=True
    )
    refresh_token: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    client_id: Mapped[int] = mapped_column(ForeignKey(OAuth2Client.id))

    client: Mapped['OAuth2Client'] = relationship(
        back_populates='tokens', init=False
    )
    user: Mapped[User] = relationship(init=False)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    revoked: Mapped[bool] = mapped_column(default=False)
