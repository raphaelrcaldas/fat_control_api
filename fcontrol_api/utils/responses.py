from typing import TypeVar

from fcontrol_api.schemas.response import (
    ApiPaginatedResponse,
    ApiResponse,
    ResponseStatus,
)

T = TypeVar('T')


def success_response(
    data: T | None = None,
    message: str | None = None,
) -> ApiResponse[T]:
    """Cria uma resposta de sucesso padronizada."""
    return ApiResponse(
        status=ResponseStatus.SUCCESS,
        data=data,
        message=message,
    )


def paginated_response(
    items: list[T],
    total: int,
    page: int,
    per_page: int,
    message: str | None = None,
) -> ApiPaginatedResponse[T]:
    """Cria uma resposta paginada padronizada."""
    pages = (total + per_page - 1) // per_page if total > 0 else 1
    return ApiPaginatedResponse(
        status=ResponseStatus.SUCCESS,
        data=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        message=message,
    )
