"""Global DB client facade.

Default backend is local PostgreSQL (`DB_BACKEND=postgres`) while keeping
Supabase SDK compatibility for legacy scripts that explicitly pass URL+KEY
into `init_client`.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.db.pool import get_pool

_client: Any | None = None
_backend: str | None = None
_table_column_types: dict[str, dict[str, str]] = {}
_table_pk_columns: dict[str, list[str]] = {}


@dataclass(slots=True)
class QueryResponse:
    """Supabase-like response object used by existing services."""

    data: list[dict[str, Any]]
    count: int | None = None


class _PgTableQuery:
    def __init__(self, table: str):
        self._table = table
        self._op = "select"
        self._select_cols = "*"
        self._need_count = False
        self._filters: list[tuple[str, list[Any]]] = []
        self._orders: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._on_conflict: str | None = None
        self._ignore_duplicates = False

    def select(self, columns: str = "*", count: str | None = None):
        self._op = "select"
        self._select_cols = columns or "*"
        self._need_count = count == "exact"
        return self

    def insert(self, values: dict[str, Any] | list[dict[str, Any]]):
        self._op = "insert"
        self._payload = values
        return self

    def upsert(
        self,
        values: dict[str, Any] | list[dict[str, Any]],
        *,
        on_conflict: str | None = None,
        ignore_duplicates: bool = False,
    ):
        self._op = "upsert"
        self._payload = values
        self._on_conflict = on_conflict
        self._ignore_duplicates = ignore_duplicates
        return self

    def update(self, values: dict[str, Any]):
        self._op = "update"
        self._payload = values
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, column: str, value: Any):
        col = _quote_ident(column)
        if value is None:
            self._filters.append((f"{col} IS NULL", []))
        else:
            self._filters.append((f"{col} = {{}}", [value]))
        return self

    def neq(self, column: str, value: Any):
        col = _quote_ident(column)
        if value is None:
            self._filters.append((f"{col} IS NOT NULL", []))
        else:
            self._filters.append((f"{col} <> {{}}", [value]))
        return self

    def ilike(self, column: str, value: str):
        self._filters.append((f"{_quote_ident(column)} ILIKE {{}}", [value]))
        return self

    def like(self, column: str, value: str):
        self._filters.append((f"{_quote_ident(column)} LIKE {{}}", [value]))
        return self

    def gte(self, column: str, value: Any):
        self._filters.append((f"{_quote_ident(column)} >= {{}}", [value]))
        return self

    def lte(self, column: str, value: Any):
        self._filters.append((f"{_quote_ident(column)} <= {{}}", [value]))
        return self

    def gt(self, column: str, value: Any):
        self._filters.append((f"{_quote_ident(column)} > {{}}", [value]))
        return self

    def lt(self, column: str, value: Any):
        self._filters.append((f"{_quote_ident(column)} < {{}}", [value]))
        return self

    def contains(self, column: str, value: Any):
        # Supports both JSONB and array fields.
        self._filters.append((f"to_jsonb({_quote_ident(column)}) @> {{}}::jsonb", [json.dumps(value, ensure_ascii=False)]))
        return self

    def or_(self, expression: str):
        conds: list[str] = []
        vals: list[Any] = []
        for raw in expression.split(","):
            token = raw.strip()
            if not token:
                continue
            col, op, val = _parse_or_token(token)
            col_sql = _quote_ident(col)
            if op == "eq":
                if val is None:
                    conds.append(f"{col_sql} IS NULL")
                else:
                    conds.append(f"{col_sql} = {{}}")
                    vals.append(val)
            elif op == "neq":
                if val is None:
                    conds.append(f"{col_sql} IS NOT NULL")
                else:
                    conds.append(f"{col_sql} <> {{}}")
                    vals.append(val)
            elif op == "ilike":
                conds.append(f"{col_sql} ILIKE {{}}")
                vals.append(str(val))
            elif op == "like":
                conds.append(f"{col_sql} LIKE {{}}")
                vals.append(str(val))
            elif op == "gte":
                conds.append(f"{col_sql} >= {{}}")
                vals.append(val)
            elif op == "lte":
                conds.append(f"{col_sql} <= {{}}")
                vals.append(val)
            elif op == "gt":
                conds.append(f"{col_sql} > {{}}")
                vals.append(val)
            elif op == "lt":
                conds.append(f"{col_sql} < {{}}")
                vals.append(val)
            else:
                raise ValueError(f"Unsupported or_ operator: {op}")

        if conds:
            self._filters.append(("(" + " OR ".join(conds) + ")", vals))
        return self

    def order(self, column: str, *, desc: bool = False):
        self._orders.append((column, desc))
        return self

    def limit(self, size: int):
        self._limit = max(0, int(size))
        return self

    def range(self, start: int, end: int):
        s = max(0, int(start))
        e = int(end)
        self._offset = s
        self._limit = max(0, e - s + 1)
        return self

    async def execute(self) -> QueryResponse:
        if self._op == "select":
            return await self._execute_select()
        if self._op == "insert":
            return await self._execute_insert(upsert=False)
        if self._op == "upsert":
            return await self._execute_insert(upsert=True)
        if self._op == "update":
            return await self._execute_update()
        if self._op == "delete":
            return await self._execute_delete()
        raise ValueError(f"Unsupported operation: {self._op}")

    async def _execute_select(self) -> QueryResponse:
        table = _quote_ident(self._table)
        select_cols = _render_select_cols(self._select_cols)
        column_types = await _get_table_column_types(self._table)

        where_sql, where_params = _compile_filters(self._filters)
        order_sql = _render_order_by(self._orders)

        sql = f"SELECT {select_cols} FROM {table}{where_sql}{order_sql}"
        params = list(where_params)

        if self._limit is not None:
            params.append(self._limit)
            sql += f" LIMIT ${len(params)}"
        if self._offset is not None:
            params.append(self._offset)
            sql += f" OFFSET ${len(params)}"

        pool = get_pool()
        records = await pool.fetch(sql, *params)
        rows = [_normalize_row(dict(r), column_types) for r in records]

        total: int | None = None
        if self._need_count:
            count_sql = f"SELECT COUNT(*)::bigint AS n FROM {table}{where_sql}"
            count_row = await pool.fetchrow(count_sql, *where_params)
            total = int(count_row["n"]) if count_row else 0

        return QueryResponse(data=rows, count=total)

    async def _execute_insert(self, *, upsert: bool) -> QueryResponse:
        rows = _normalize_rows(self._payload)
        if not rows:
            return QueryResponse(data=[])

        table = _quote_ident(self._table)
        cols = list(rows[0].keys())
        cols_sql = ", ".join(_quote_ident(c) for c in cols)
        column_types = await _get_table_column_types(self._table)

        values_sql: list[str] = []
        params: list[Any] = []
        for row in rows:
            placeholders: list[str] = []
            for col in cols:
                value, cast_sql = _coerce_param(row.get(col), column_types.get(col))
                params.append(value)
                placeholders.append(f"${len(params)}{cast_sql}")
            values_sql.append("(" + ", ".join(placeholders) + ")")

        sql = f"INSERT INTO {table} ({cols_sql}) VALUES " + ", ".join(values_sql)

        if upsert:
            conflict_cols = [c.strip() for c in (self._on_conflict or "").split(",") if c.strip()]
            if not conflict_cols:
                conflict_cols = await _get_table_pk_columns(self._table)
            if conflict_cols:
                conflict_sql = ", ".join(_quote_ident(c) for c in conflict_cols)
                sql += f" ON CONFLICT ({conflict_sql})"
                non_conflict = [c for c in cols if c not in conflict_cols]
                if self._ignore_duplicates or not non_conflict:
                    sql += " DO NOTHING"
                else:
                    set_sql = ", ".join(
                        f"{_quote_ident(c)} = EXCLUDED.{_quote_ident(c)}" for c in non_conflict
                    )
                    sql += f" DO UPDATE SET {set_sql}"
            elif self._ignore_duplicates:
                sql += " ON CONFLICT DO NOTHING"

        sql += " RETURNING *"

        pool = get_pool()
        records = await pool.fetch(sql, *params)
        column_types = await _get_table_column_types(self._table)
        return QueryResponse(data=[_normalize_row(dict(r), column_types) for r in records])

    async def _execute_update(self) -> QueryResponse:
        updates = self._payload if isinstance(self._payload, dict) else {}
        if not updates:
            return QueryResponse(data=[])

        table = _quote_ident(self._table)
        column_types = await _get_table_column_types(self._table)
        params: list[Any] = []
        set_parts: list[str] = []
        for col, value in updates.items():
            coerced, cast_sql = _coerce_param(value, column_types.get(col))
            params.append(coerced)
            set_parts.append(f"{_quote_ident(col)} = ${len(params)}{cast_sql}")

        where_sql, where_params = _compile_filters(self._filters, start_index=len(params) + 1)
        params.extend(where_params)

        sql = f"UPDATE {table} SET {', '.join(set_parts)}{where_sql} RETURNING *"
        pool = get_pool()
        records = await pool.fetch(sql, *params)
        return QueryResponse(data=[_normalize_row(dict(r), column_types) for r in records])

    async def _execute_delete(self) -> QueryResponse:
        table = _quote_ident(self._table)
        where_sql, params = _compile_filters(self._filters)
        sql = f"DELETE FROM {table}{where_sql} RETURNING *"
        pool = get_pool()
        records = await pool.fetch(sql, *params)
        column_types = await _get_table_column_types(self._table)
        return QueryResponse(data=[_normalize_row(dict(r), column_types) for r in records])


class LocalPostgresClient:
    """Minimal Supabase-style facade on top of asyncpg."""

    def table(self, name: str) -> _PgTableQuery:
        return _PgTableQuery(name)


def _quote_ident(name: str) -> str:
    if not name or not all(ch.isalnum() or ch == "_" for ch in name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return '"' + name + '"'


def _normalize_rows(payload: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return payload
    raise TypeError("Payload must be dict or list[dict]")


def _render_select_cols(columns: str) -> str:
    raw = (columns or "*").strip()
    if raw == "*":
        return "*"
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return "*"
    return ", ".join(_quote_ident(p) for p in parts)


def _render_order_by(orders: list[tuple[str, bool]]) -> str:
    if not orders:
        return ""
    segs = [f"{_quote_ident(col)} {'DESC' if desc else 'ASC'}" for col, desc in orders]
    return " ORDER BY " + ", ".join(segs)


def _compile_template(template: str, values: list[Any], start_index: int) -> tuple[str, int]:
    parts = template.split("{}")
    if len(parts) - 1 != len(values):
        raise ValueError("Placeholder/value length mismatch")
    out = [parts[0]]
    idx = start_index
    for i in range(len(values)):
        out.append(f"${idx}")
        out.append(parts[i + 1])
        idx += 1
    return "".join(out), idx


def _compile_filters(
    filters: list[tuple[str, list[Any]]],
    *,
    start_index: int = 1,
) -> tuple[str, list[Any]]:
    if not filters:
        return "", []

    sql_parts: list[str] = []
    params: list[Any] = []
    idx = start_index
    for template, values in filters:
        sql, idx = _compile_template(template, values, idx)
        sql_parts.append(sql)
        params.extend(values)

    return " WHERE " + " AND ".join(sql_parts), params


def _parse_or_token(token: str) -> tuple[str, str, Any]:
    # Supabase style token: "column.operator.value"
    parts = token.split(".", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid or_ token: {token!r}")
    col, op, raw_val = parts[0].strip(), parts[1].strip(), parts[2]
    if op in {"ilike", "like"}:
        return col, op, raw_val
    return col, op, _parse_scalar(raw_val)


def _parse_scalar(value: str) -> Any:
    v = value.strip()
    low = v.lower()
    if low == "null":
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


async def _get_table_column_types(table: str) -> dict[str, str]:
    cached = _table_column_types.get(table)
    if cached is not None:
        return cached

    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    mapping: dict[str, str] = {}
    for r in rows:
        col = str(r["column_name"])
        data_type = str(r["data_type"])
        udt_name = str(r["udt_name"])
        mapping[col] = f"{data_type}|{udt_name}"
    _table_column_types[table] = mapping
    return mapping


async def _get_table_pk_columns(table: str) -> list[str]:
    cached = _table_pk_columns.get(table)
    if cached is not None:
        return cached

    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.table_schema = 'public'
          AND tc.table_name = $1
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """,
        table,
    )
    cols = [str(r["column_name"]) for r in rows]
    _table_pk_columns[table] = cols
    return cols


def _coerce_param(value: Any, column_meta: str | None) -> tuple[Any, str]:
    """Return (param_value, explicit_cast_sql)."""
    if value is None or not column_meta:
        return value, ""

    data_type, _, udt_name = column_meta.partition("|")

    if data_type in {"timestamp with time zone", "timestamp without time zone"} and isinstance(value, str):
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed, ""
        return value, "::timestamptz" if data_type == "timestamp with time zone" else "::timestamp"
    if data_type == "date" and isinstance(value, str):
        parsed_date = _parse_date(value)
        if parsed_date is not None:
            return parsed_date, ""
        return value, "::date"
    if data_type in {"json", "jsonb"}:
        if isinstance(value, str):
            return value, "::jsonb" if data_type == "jsonb" else "::json"
        return (
            json.dumps(value, ensure_ascii=False),
            "::jsonb" if data_type == "jsonb" else "::json",
        )
    # For array columns asyncpg already accepts Python lists.
    if udt_name.startswith("_"):
        return value, ""
    return value, ""


def _normalize_row(row: dict[str, Any], column_types: dict[str, str]) -> dict[str, Any]:
    for col, value in list(row.items()):
        if value is None:
            continue
        meta = column_types.get(col)
        if not meta:
            continue
        data_type, _, _ = meta.partition("|")

        # Keep compatibility with Supabase REST payload format.
        if isinstance(value, (datetime, date)):
            row[col] = value.isoformat()
            continue

        if data_type in {"json", "jsonb"} and isinstance(value, str):
            text = value.strip()
            if not text:
                row[col] = {} if data_type == "jsonb" else None
                continue
            try:
                row[col] = json.loads(text)
            except json.JSONDecodeError:
                # Keep original string if not valid JSON text.
                pass
    return row


def _parse_datetime(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_date(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


async def init_client(
    url: str | None = None,
    key: str | None = None,
    *,
    backend: str | None = None,
) -> None:
    """Initialize global DB client.

    - If `url` and `key` are provided, Supabase backend is used for compatibility.
    - Otherwise backend defaults to `settings.DB_BACKEND` (postgres by default).
    """
    global _client, _backend
    if _client is not None:
        return

    selected = (backend or "").strip().lower()
    if not selected:
        selected = "supabase" if (url and key) else settings.DB_BACKEND.strip().lower()

    if selected in {"postgres", "postgresql", "local"}:
        # Ensure pool is already initialized by app startup.
        get_pool()
        _client = LocalPostgresClient()
        _backend = "postgres"
        return

    if selected == "supabase":
        supabase_url = url or settings.SUPABASE_URL
        supabase_key = key or settings.SUPABASE_KEY
        if not supabase_url or not supabase_key:
            raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY for supabase backend")
        from supabase import create_async_client  # lazy import

        _client = await create_async_client(supabase_url, supabase_key)
        _backend = "supabase"
        return

    raise RuntimeError(f"Unsupported DB backend: {selected}")


async def close_client() -> None:
    """Close and reset global client."""
    global _client, _backend
    _client = None
    _backend = None
    _table_column_types.clear()
    _table_pk_columns.clear()


def get_client() -> Any:
    """Return the active client. Raises RuntimeError if not initialized."""
    if _client is None:
        raise RuntimeError("DB client not initialized. Call init_client() first.")
    return _client
