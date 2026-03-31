"""Global student APIs backed by supervised_students table."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.pool import get_pool
from app.schemas.student import (
    StudentCreateRequest,
    StudentDetailResponse,
    StudentFilterOptions,
    StudentListItem,
    StudentListResponse,
    StudentUpdateRequest,
)

router = APIRouter()

UNKNOWN_MENTOR_SCHOLAR_ID = "__unknown_student_mentor__"
UNKNOWN_MENTOR_SCHOLAR_NAME = "待匹配导师"

_TEXT_FIELDS: dict[str, str] = {
    "student_no": "student_no",
    "name": "name",
    "home_university": "home_university",
    "major": "major",
    "degree_type": "degree_type",
    "status": "status",
    "email": "email",
    "phone": "phone",
    "notes": "notes",
    "mentor_name": "mentor_name",
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _to_year(value: Any) -> int | None:
    token = _clean_text(value)
    if not token:
        return None
    try:
        year = int(float(token))
    except ValueError:
        digits = "".join(ch for ch in token if ch.isdigit())
        if len(digits) < 4:
            return None
        year = int(digits[:4])
    if year < 1900 or year > 2100:
        return None
    return year


def _normalize_added_by(raw_added_by: Any) -> str:
    token = _clean_text(raw_added_by)
    if not token:
        return "user:unknown"
    if token.startswith("user:") or token.startswith("system:"):
        return token
    return f"user:{token}"


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _clean_text(value)


def _to_student_list_item(row: dict[str, Any]) -> StudentListItem:
    enrollment_year = row.get("enrollment_year")
    return StudentListItem(
        id=_clean_text(row.get("id")),
        scholar_id=_clean_text(row.get("scholar_id")),
        student_no=_clean_text(row.get("student_no")),
        name=_clean_text(row.get("name")),
        home_university=_clean_text(row.get("home_university")),
        enrollment_year="" if enrollment_year is None else str(enrollment_year),
        status=_clean_text(row.get("status")) or "在读",
        email=_clean_text(row.get("email")),
        phone=_clean_text(row.get("phone")),
        major=_clean_text(row.get("major")),
        mentor_name=_clean_text(row.get("mentor_name")),
    )


def _to_student_detail(row: dict[str, Any]) -> StudentDetailResponse:
    base = _to_student_list_item(row)
    enrollment_year = row.get("enrollment_year")
    expected_graduation_year = row.get("expected_graduation_year")
    return StudentDetailResponse(
        id=base.id,
        student_no=base.student_no,
        name=base.name,
        home_university=base.home_university,
        major=base.major,
        enrollment_year="" if enrollment_year is None else str(enrollment_year),
        status=base.status,
        email=base.email,
        phone=base.phone,
        mentor_name=base.mentor_name,
        degree_type=_clean_text(row.get("degree_type")),
        expected_graduation_year=(
            "" if expected_graduation_year is None else str(expected_graduation_year)
        ),
        added_by=_normalize_added_by(row.get("added_by")),
        created_at=_iso(row.get("created_at")),
        updated_at=_iso(row.get("updated_at")),
    )


async def _ensure_placeholder_scholar() -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO scholars (id, name)
        VALUES ($1, $2)
        ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name,
            updated_at = now()
        """,
        UNKNOWN_MENTOR_SCHOLAR_ID,
        UNKNOWN_MENTOR_SCHOLAR_NAME,
    )


async def _resolve_scholar_ref(
    scholar_id: str | None,
    mentor_name: str | None,
    home_university: str | None = None,
) -> tuple[str, str]:
    await _ensure_placeholder_scholar()
    pool = get_pool()

    provided_id = _clean_text(scholar_id)
    if provided_id:
        row = await pool.fetchrow(
            """
            SELECT id, name
            FROM scholars
            WHERE id = $1
            LIMIT 1
            """,
            provided_id,
        )
        if row:
            return _clean_text(row["id"]), _clean_text(row["name"])

    mentor = _clean_text(mentor_name)
    home_uni = _clean_text(home_university)
    if mentor:
        normalized_mentor = (
            mentor.lower()
            .replace(" ", "")
            .replace("\u3000", "")
            .replace("·", "")
            .replace("•", "")
        )
        row = await pool.fetchrow(
            """
            SELECT id, name
            FROM scholars
            WHERE name = $1
               OR lower(
                    replace(
                      replace(
                        replace(
                          replace(COALESCE(name, ''), ' ', ''),
                        '　', ''),
                      '·', ''),
                    '•', '')
                  ) = $2
            ORDER BY
              CASE
                WHEN $3 <> ''
                 AND COALESCE(university, '') ILIKE ('%' || $3 || '%')
                THEN 0
                ELSE 1
              END ASC,
              CASE
                WHEN project_category = '教育培养'
                 AND project_subcategory IN ('学院学生高校导师', '兼职导师')
                THEN 0
                ELSE 1
              END ASC,
              CASE WHEN COALESCE(email, '') <> '' THEN 0 ELSE 1 END ASC,
              id ASC
            LIMIT 1
            """,
            mentor,
            normalized_mentor,
            home_uni,
        )
        if row:
            return _clean_text(row["id"]), _clean_text(row["name"])

    return UNKNOWN_MENTOR_SCHOLAR_ID, UNKNOWN_MENTOR_SCHOLAR_NAME


def _build_list_where(
    institution: str | None,
    enrollment_year: str | None,
    name: str | None,
    email: str | None,
    student_no: str | None,
    status: str | None,
    mentor_name: str | None,
    keyword: str | None,
) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    year = _to_year(enrollment_year)
    if year is not None:
        params.append(year)
        conditions.append(f"s.enrollment_year = ${len(params)}")

    if _clean_text(institution):
        params.append(f"%{_clean_text(institution)}%")
        conditions.append(f"COALESCE(s.home_university, '') ILIKE ${len(params)}")

    if _clean_text(name):
        params.append(f"%{_clean_text(name)}%")
        conditions.append(f"COALESCE(s.name, '') ILIKE ${len(params)}")

    if _clean_text(email):
        params.append(f"%{_clean_text(email)}%")
        conditions.append(f"COALESCE(s.email, '') ILIKE ${len(params)}")

    if _clean_text(student_no):
        params.append(f"%{_clean_text(student_no)}%")
        conditions.append(f"COALESCE(s.student_no, '') ILIKE ${len(params)}")

    if _clean_text(status):
        params.append(_clean_text(status))
        conditions.append(
            f"COALESCE(NULLIF(s.status, ''), '在读') = ${len(params)}"
        )

    if _clean_text(mentor_name):
        params.append(f"%{_clean_text(mentor_name)}%")
        p = len(params)
        conditions.append(
            f"(COALESCE(s.mentor_name, '') ILIKE ${p} OR COALESCE(m.name, '') ILIKE ${p})"
        )

    if _clean_text(keyword):
        params.append(f"%{_clean_text(keyword)}%")
        p = len(params)
        conditions.append(
            "("
            f"COALESCE(s.name, '') ILIKE ${p} OR "
            f"COALESCE(s.student_no, '') ILIKE ${p} OR "
            f"COALESCE(s.home_university, '') ILIKE ${p} OR "
            f"COALESCE(s.major, '') ILIKE ${p} OR "
            f"COALESCE(s.email, '') ILIKE ${p} OR "
            f"COALESCE(s.mentor_name, '') ILIKE ${p} OR "
            f"COALESCE(m.name, '') ILIKE ${p}"
            ")"
        )

    if not conditions:
        return "", params
    return " WHERE " + " AND ".join(conditions), params


async def _fetch_student_row(student_id: str) -> dict[str, Any] | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT
          s.id,
          CASE
            WHEN s.scholar_id = '__unknown_student_mentor__' THEN COALESCE(
              (
                SELECT m2.id
                FROM scholars m2
                WHERE COALESCE(s.mentor_name, '') <> ''
                  AND (
                    m2.name = s.mentor_name
                    OR lower(
                        replace(
                          replace(
                            replace(
                              replace(COALESCE(m2.name, ''), ' ', ''),
                            '　', ''),
                          '·', ''),
                        '•', '')
                      ) = lower(
                        replace(
                          replace(
                            replace(
                              replace(COALESCE(s.mentor_name, ''), ' ', ''),
                            '　', ''),
                          '·', ''),
                        '•', '')
                      )
                  )
                ORDER BY
                  CASE
                    WHEN COALESCE(s.home_university, '') <> ''
                     AND COALESCE(m2.university, '') ILIKE ('%' || s.home_university || '%')
                    THEN 0
                    ELSE 1
                  END ASC,
                  CASE
                    WHEN m2.project_category = '教育培养'
                     AND m2.project_subcategory IN ('学院学生高校导师', '兼职导师')
                    THEN 0
                    ELSE 1
                  END ASC,
                  CASE WHEN COALESCE(m2.email, '') <> '' THEN 0 ELSE 1 END ASC,
                  m2.id ASC
                LIMIT 1
              ),
              s.scholar_id
            )
            ELSE s.scholar_id
          END AS scholar_id,
          COALESCE(
            NULLIF(s.student_no, ''),
            (
              SELECT NULLIF(s2.student_no, '')
              FROM supervised_students s2
              WHERE s2.id <> s.id
                AND COALESCE(s2.name, '') = COALESCE(s.name, '')
                AND (
                  s2.enrollment_year IS NOT DISTINCT FROM s.enrollment_year
                  OR COALESCE(s2.home_university, '') = COALESCE(s.home_university, '')
                )
                AND COALESCE(s2.student_no, '') <> ''
              ORDER BY
                CASE WHEN s2.enrollment_year IS NOT DISTINCT FROM s.enrollment_year THEN 0 ELSE 1 END ASC,
                CASE WHEN COALESCE(s2.home_university, '') = COALESCE(s.home_university, '') THEN 0 ELSE 1 END ASC,
                s2.updated_at DESC
              LIMIT 1
            ),
            ''
          ) AS student_no,
          s.name,
          s.home_university,
          s.enrollment_year,
          s.status,
          s.email,
          s.phone,
          s.major,
          COALESCE(NULLIF(s.mentor_name, ''), m.name, '') AS mentor_name,
          s.degree_type,
          s.expected_graduation_year,
          s.added_by,
          s.created_at,
          s.updated_at
        FROM supervised_students s
        LEFT JOIN scholars m ON m.id = s.scholar_id
        WHERE s.id = $1
        LIMIT 1
        """,
        student_id,
    )
    if not row:
        return None
    return dict(row)


@router.get(
    "",
    response_model=StudentListResponse,
    summary="学生列表",
    description="按年级/高校/导师/关键词筛选学生，返回分页列表。",
)
async def list_students(
    institution: str | None = Query(None, description="机构/共建高校（模糊匹配）"),
    grade: str | None = Query(None, description="兼容参数：年级，如 2025"),
    enrollment_year: str | None = Query(None, description="入学年级，如 2024 或 2024级"),
    home_university: str | None = Query(None, description="兼容参数：共建高校（模糊匹配）"),
    mentor_name: str | None = Query(
        None,
        description="导师姓名（匹配 mentor_name 或关联 scholar 名称）",
    ),
    name: str | None = Query(None, description="学生姓名（模糊匹配）"),
    email: str | None = Query(None, description="邮箱（模糊匹配）"),
    student_no: str | None = Query(None, description="学号（模糊匹配）"),
    status: str | None = Query(None, description="在读状态（如 在读/毕业）"),
    keyword: str | None = Query(None, description="关键词（姓名/学号/学校/导师/邮箱）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=500, description="每页条数"),
):
    await _ensure_placeholder_scholar()
    pool = get_pool()
    institution_filter = institution or home_university
    year_filter = enrollment_year or grade
    where_sql, params = _build_list_where(
        institution=institution_filter,
        enrollment_year=year_filter,
        name=name,
        email=email,
        student_no=student_no,
        status=status,
        mentor_name=mentor_name,
        keyword=keyword,
    )

    count_sql = (
        "SELECT COUNT(*)::bigint "
        "FROM supervised_students s "
        "LEFT JOIN scholars m ON m.id = s.scholar_id"
        f"{where_sql}"
    )
    total = int(await pool.fetchval(count_sql, *params) or 0)

    offset = (page - 1) * page_size
    data_params = [*params, page_size, offset]
    limit_idx = len(params) + 1
    offset_idx = len(params) + 2
    order_sql = (
        " ORDER BY s.enrollment_year DESC NULLS LAST,"
        f" s.created_at DESC LIMIT ${limit_idx} OFFSET ${offset_idx}"
    )
    rows = await pool.fetch(
        """
        SELECT
          s.id,
          CASE
            WHEN s.scholar_id = '__unknown_student_mentor__' THEN COALESCE(
              (
                SELECT m2.id
                FROM scholars m2
                WHERE COALESCE(s.mentor_name, '') <> ''
                  AND (
                    m2.name = s.mentor_name
                    OR lower(
                        replace(
                          replace(
                            replace(
                              replace(COALESCE(m2.name, ''), ' ', ''),
                            '　', ''),
                          '·', ''),
                        '•', '')
                      ) = lower(
                        replace(
                          replace(
                            replace(
                              replace(COALESCE(s.mentor_name, ''), ' ', ''),
                            '　', ''),
                          '·', ''),
                        '•', '')
                      )
                  )
                ORDER BY
                  CASE
                    WHEN COALESCE(s.home_university, '') <> ''
                     AND COALESCE(m2.university, '') ILIKE ('%' || s.home_university || '%')
                    THEN 0
                    ELSE 1
                  END ASC,
                  CASE
                    WHEN m2.project_category = '教育培养'
                     AND m2.project_subcategory IN ('学院学生高校导师', '兼职导师')
                    THEN 0
                    ELSE 1
                  END ASC,
                  CASE WHEN COALESCE(m2.email, '') <> '' THEN 0 ELSE 1 END ASC,
                  m2.id ASC
                LIMIT 1
              ),
              s.scholar_id
            )
            ELSE s.scholar_id
          END AS scholar_id,
          COALESCE(
            NULLIF(s.student_no, ''),
            (
              SELECT NULLIF(s2.student_no, '')
              FROM supervised_students s2
              WHERE s2.id <> s.id
                AND COALESCE(s2.name, '') = COALESCE(s.name, '')
                AND (
                  s2.enrollment_year IS NOT DISTINCT FROM s.enrollment_year
                  OR COALESCE(s2.home_university, '') = COALESCE(s.home_university, '')
                )
                AND COALESCE(s2.student_no, '') <> ''
              ORDER BY
                CASE WHEN s2.enrollment_year IS NOT DISTINCT FROM s.enrollment_year THEN 0 ELSE 1 END ASC,
                CASE WHEN COALESCE(s2.home_university, '') = COALESCE(s.home_university, '') THEN 0 ELSE 1 END ASC,
                s2.updated_at DESC
              LIMIT 1
            ),
            ''
          ) AS student_no,
          s.name,
          s.home_university,
          s.enrollment_year,
          s.status,
          s.email,
          s.phone,
          s.major,
          COALESCE(NULLIF(s.mentor_name, ''), m.name, '') AS mentor_name
        FROM supervised_students s
        LEFT JOIN scholars m ON m.id = s.scholar_id
        """
        + where_sql
        + order_sql,
        *data_params,
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return StudentListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=[_to_student_list_item(dict(row)) for row in rows],
    )


@router.get(
    "/options",
    response_model=StudentFilterOptions,
    summary="学生筛选项",
    description="返回年级、高校、导师筛选值。可按年级限制高校/导师选项。",
)
async def get_filter_options(
    enrollment_year: str | None = Query(None, description="可选，按某个年级返回高校/导师选项"),
):
    await _ensure_placeholder_scholar()
    pool = get_pool()
    year = _to_year(enrollment_year)

    grade_rows = await pool.fetch(
        """
        SELECT DISTINCT enrollment_year
        FROM supervised_students
        WHERE enrollment_year IS NOT NULL
        ORDER BY enrollment_year DESC
        """
    )
    grades = [str(row["enrollment_year"]) for row in grade_rows]

    filter_sql = ""
    params: list[Any] = []
    if year is not None:
        params = [year]
        filter_sql = " AND s.enrollment_year = $1"

    uni_rows = await pool.fetch(
        """
        SELECT DISTINCT COALESCE(s.home_university, '') AS value
        FROM supervised_students s
        WHERE COALESCE(s.home_university, '') <> ''
        """
        + filter_sql
        + " ORDER BY value ASC",
        *params,
    )
    universities = [_clean_text(row["value"]) for row in uni_rows if _clean_text(row["value"])]

    mentor_rows = await pool.fetch(
        """
        SELECT DISTINCT COALESCE(NULLIF(s.mentor_name, ''), m.name, '') AS value
        FROM supervised_students s
        LEFT JOIN scholars m ON m.id = s.scholar_id
        WHERE COALESCE(NULLIF(s.mentor_name, ''), m.name, '') <> ''
        """
        + filter_sql
        + " ORDER BY value ASC",
        *params,
    )
    mentors = [_clean_text(row["value"]) for row in mentor_rows if _clean_text(row["value"])]

    return StudentFilterOptions(
        grades=grades,
        universities=universities,
        mentors=mentors,
    )


@router.get(
    "/{student_id}",
    response_model=StudentDetailResponse,
    summary="学生详情",
)
async def get_student(student_id: str):
    row = await _fetch_student_row(student_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
    return _to_student_detail(row)


@router.post(
    "",
    response_model=StudentDetailResponse,
    status_code=201,
    summary="新增学生",
)
async def create_student(body: StudentCreateRequest):
    scholar_id, resolved_scholar_name = await _resolve_scholar_ref(
        body.scholar_id,
        body.mentor_name,
        body.home_university,
    )
    mentor_name = _clean_text(body.mentor_name)
    if not mentor_name and scholar_id != UNKNOWN_MENTOR_SCHOLAR_ID:
        mentor_name = resolved_scholar_name

    pool = get_pool()
    inserted = await pool.fetchrow(
        """
        INSERT INTO supervised_students
        (scholar_id, student_no, name, home_university, major, degree_type,
         enrollment_year, expected_graduation_year, status, email, phone, notes,
         mentor_name, added_by)
        VALUES
        ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        RETURNING id
        """,
        scholar_id,
        _clean_text(body.student_no) or None,
        _clean_text(body.name),
        _clean_text(body.home_university) or None,
        _clean_text(body.major) or None,
        _clean_text(body.degree_type) or None,
        _to_year(body.enrollment_year),
        _to_year(body.expected_graduation_year),
        _clean_text(body.status) or "在读",
        _clean_text(body.email) or None,
        _clean_text(body.phone) or None,
        _clean_text(body.notes) or None,
        mentor_name or None,
        _normalize_added_by(body.added_by),
    )
    if inserted is None:
        raise HTTPException(status_code=500, detail="Failed to create student")

    row = await _fetch_student_row(_clean_text(inserted["id"]))
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to fetch created student")
    return _to_student_detail(row)


@router.patch(
    "/{student_id}",
    response_model=StudentDetailResponse,
    summary="更新学生",
)
async def update_student(student_id: str, body: StudentUpdateRequest):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        row = await _fetch_student_row(student_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
        return _to_student_detail(row)

    pool = get_pool()
    current_row = await pool.fetchrow(
        """
        SELECT id, scholar_id, mentor_name, home_university
        FROM supervised_students
        WHERE id = $1
        LIMIT 1
        """,
        student_id,
    )
    if current_row is None:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")

    patch: dict[str, Any] = {}
    if "scholar_id" in updates or "mentor_name" in updates:
        requested_scholar_id = _clean_text(updates.get("scholar_id"))
        requested_mentor_name = (
            _clean_text(updates.get("mentor_name"))
            if "mentor_name" in updates
            else _clean_text(current_row["mentor_name"])
        )
        home_university = (
            _clean_text(updates.get("home_university"))
            if "home_university" in updates
            else _clean_text(current_row["home_university"])
        )
        resolved_id, resolved_name = await _resolve_scholar_ref(
            requested_scholar_id or None,
            requested_mentor_name or None,
            home_university or None,
        )
        patch["scholar_id"] = resolved_id
        if "mentor_name" in updates:
            mentor_name = requested_mentor_name
            if not mentor_name and resolved_id != UNKNOWN_MENTOR_SCHOLAR_ID:
                mentor_name = resolved_name
            patch["mentor_name"] = mentor_name or None

    for req_key, db_key in _TEXT_FIELDS.items():
        if req_key in {"mentor_name"}:
            continue
        if req_key not in updates:
            continue
        value = _clean_text(updates.get(req_key))
        if db_key in {"name", "status"}:
            patch[db_key] = value
        else:
            patch[db_key] = value or None

    if "enrollment_year" in updates:
        patch["enrollment_year"] = _to_year(updates.get("enrollment_year"))
    if "expected_graduation_year" in updates:
        patch["expected_graduation_year"] = _to_year(updates.get("expected_graduation_year"))

    if not patch:
        row = await _fetch_student_row(student_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
        return _to_student_detail(row)

    params: list[Any] = [student_id]
    assignments: list[str] = []
    for key, value in patch.items():
        params.append(value)
        assignments.append(f"{key} = ${len(params)}")
    params.append(datetime.now(timezone.utc))
    assignments.append(f"updated_at = ${len(params)}")

    await pool.execute(
        f"UPDATE supervised_students SET {', '.join(assignments)} WHERE id = $1",
        *params,
    )

    row = await _fetch_student_row(student_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
    return _to_student_detail(row)


@router.delete(
    "/{student_id}",
    status_code=204,
    summary="删除学生",
)
async def delete_student(student_id: str):
    pool = get_pool()
    result = await pool.execute(
        """
        DELETE FROM supervised_students
        WHERE id = $1
        """,
        student_id,
    )
    deleted = int(result.split()[-1]) if result else 0
    if deleted <= 0:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
