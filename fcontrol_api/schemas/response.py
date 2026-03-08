from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar('T')


class ResponseStatus(str, Enum):
    """Status padronizado para respostas da API."""

    SUCCESS = 'success'
    ERROR = 'error'
    WARNING = 'warning'


class ApiResponse(BaseModel, Generic[T]):
    """Wrapper genérico para todas as respostas da API."""

    status: ResponseStatus = ResponseStatus.SUCCESS
    data: T | None = None
    message: str | None = None
    errors: dict[str, Any] | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ApiPaginatedResponse(ApiResponse[list[T]], Generic[T]):
    """Wrapper para respostas paginadas."""

    total: int = 0
    page: int = 1
    per_page: int = 20
    pages: int = 1
    total_items: int | None = None


class ApiErrorResponse(BaseModel):
    """Resposta padronizada para erros."""

    status: ResponseStatus = ResponseStatus.ERROR
    message: str
    errors: dict[str, Any] | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    path: str | None = None
