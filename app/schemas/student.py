"""Pydantic schemas for global student management endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field


class StudentListItem(BaseModel):
    """Student item returned by list endpoint (optimized fields)."""

    id: str
    scholar_id: str = ""
    student_no: str = ""
    name: str
    home_university: str = ""
    enrollment_year: str = ""
    status: str = "在读"
    email: str = ""
    phone: str = ""
    major: str = ""
    mentor_name: str = ""


class StudentDetailResponse(StudentListItem):
    """Student detail response with additional editable metadata."""

    degree_type: str = ""
    expected_graduation_year: str = ""
    added_by: str = ""
    created_at: str = ""
    updated_at: str = ""


class StudentListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[StudentListItem]


class StudentCreateRequest(BaseModel):
    scholar_id: str | None = Field(
        default=None,
        description="关联学者 url_hash；为空时自动挂载到占位导师",
    )
    mentor_name: str = Field(default="", description="导师姓名（可为空）")
    student_no: str = Field(default="", description="学号")
    name: str = Field(description="学生姓名")
    home_university: str = Field(default="", description="共建高校/学籍学校")
    major: str = Field(default="", description="专业")
    degree_type: str = Field(default="", description="培养类型")
    enrollment_year: str = Field(default="", description="年级/入学年份")
    expected_graduation_year: str = Field(default="", description="预计毕业年份")
    status: str = Field(default="在读", description="状态")
    email: str = Field(default="", description="邮箱")
    phone: str = Field(default="", description="电话")
    notes: str = Field(default="", description="备注")
    added_by: str = Field(default="", description="录入人")


class StudentUpdateRequest(BaseModel):
    scholar_id: str | None = Field(default=None, description="关联学者 url_hash")
    mentor_name: str | None = Field(default=None, description="导师姓名")
    student_no: str | None = Field(default=None, description="学号")
    name: str | None = Field(default=None, description="学生姓名")
    home_university: str | None = Field(default=None, description="共建高校/学籍学校")
    major: str | None = Field(default=None, description="专业")
    degree_type: str | None = Field(default=None, description="培养类型")
    enrollment_year: str | None = Field(default=None, description="年级/入学年份")
    expected_graduation_year: str | None = Field(default=None, description="预计毕业年份")
    status: str | None = Field(default=None, description="状态")
    email: str | None = Field(default=None, description="邮箱")
    phone: str | None = Field(default=None, description="电话")
    notes: str | None = Field(default=None, description="备注")
    updated_by: str | None = Field(default=None, description="更新人")


class StudentFilterOptions(BaseModel):
    grades: list[str] = Field(default_factory=list)
    universities: list[str] = Field(default_factory=list)
    mentors: list[str] = Field(default_factory=list)
