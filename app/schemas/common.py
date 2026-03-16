from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T] = Field(description="当前页的数据列表")
    total: int = Field(description="符合条件的总记录数", examples=[156])
    page: int = Field(description="当前页码（从 1 开始）", examples=[1])
    page_size: int = Field(description="每页条数", examples=[20])
    total_pages: int = Field(description="总页数", examples=[8])


class ErrorResponse(BaseModel):
    detail: str = Field(description="错误详情", examples=["Article not found"])
