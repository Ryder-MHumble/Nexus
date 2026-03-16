"""Pydantic schemas for supervised students (/api/v1/scholars/{url_hash}/students).

These represent students in joint training programs, where the student's home
university is the original university (e.g. Peking University), and the advisor
is an adjunct/specially appointed professor at the institute.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SupervisedStudentBase(BaseModel):
    """Core fields shared across create / update / response."""

    student_no: str = Field(default="", description="学号，如 '240101003'")
    name: str = Field(description="学生姓名")
    home_university: str = Field(default="", description="所属高校（联合培养来源，如 '北京大学'）")
    degree_type: str = Field(
        default="",
        description="学历层次：'硕士' | '博士' | '博士后' | ''",
    )
    enrollment_year: str = Field(default="", description="入学年份，如 '2024'")
    expected_graduation_year: str = Field(default="", description="预计毕业年份，如 '2027'")
    status: str = Field(
        default="在读",
        description="在读状态：'在读' | '已毕业' | '已退学'",
    )
    email: str = Field(default="", description="联系邮箱")
    phone: str = Field(default="", description="联系电话")
    notes: str = Field(default="", description="补充备注")


class SupervisedStudentCreate(SupervisedStudentBase):
    """Request body for POST /scholars/{url_hash}/students."""

    added_by: str = Field(
        default="",
        description="录入人用户名，系统自动补充为 'user:{added_by}'",
    )


class SupervisedStudentUpdate(BaseModel):
    """Request body for PATCH /scholars/{url_hash}/students/{student_id}.

    All fields are optional — None means "do not modify".
    """

    student_no: str | None = Field(default=None, description="学号")
    name: str | None = Field(default=None, description="学生姓名")
    home_university: str | None = Field(default=None, description="所属高校")
    degree_type: str | None = Field(default=None, description="学历层次")
    enrollment_year: str | None = Field(default=None, description="入学年份")
    expected_graduation_year: str | None = Field(default=None, description="预计毕业年份")
    status: str | None = Field(default=None, description="在读状态")
    email: str | None = Field(default=None, description="联系邮箱")
    phone: str | None = Field(default=None, description="联系电话")
    notes: str | None = Field(default=None, description="补充备注")
    updated_by: str = Field(default="", description="操作人用户名")


class SupervisedStudentResponse(SupervisedStudentBase):
    """Single student record returned by the API."""

    id: str = Field(description="学生记录唯一 ID（UUID，服务端生成）")
    added_by: str = Field(default="", description="录入人，如 'user:admin'")
    created_at: str = Field(default="", description="录入时间 ISO8601")
    updated_at: str = Field(default="", description="最后更新时间 ISO8601")


class SupervisedStudentListResponse(BaseModel):
    """Response for GET /faculty/{url_hash}/students."""

    total: int = Field(description="该导师下的学生总数")
    faculty_url_hash: str = Field(description="导师的 url_hash")
    items: list[SupervisedStudentResponse]
