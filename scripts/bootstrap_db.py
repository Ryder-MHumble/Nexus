#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.db.bootstrap import (
    PostgresBootstrapSettings,
    bootstrap_postgres_sync,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the local PostgreSQL database and Nexus core tables."
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file to load before reading PostgreSQL settings (default: .env).",
    )
    parser.add_argument("--host", help="Override POSTGRES_HOST")
    parser.add_argument("--port", type=int, help="Override POSTGRES_PORT")
    parser.add_argument("--user", help="Override POSTGRES_USER")
    parser.add_argument("--password", help="Override POSTGRES_PASSWORD")
    parser.add_argument("--database", help="Override POSTGRES_DB")
    parser.add_argument(
        "--admin-database",
        default=os.getenv("POSTGRES_ADMIN_DB", "postgres"),
        help="Database used to create the target DB if missing (default: postgres).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable text.",
    )
    return parser.parse_args()


def load_env(env_file: str) -> None:
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path, override=True)


def make_settings(args: argparse.Namespace) -> PostgresBootstrapSettings:
    return PostgresBootstrapSettings(
        host=args.host or os.getenv("POSTGRES_HOST") or "127.0.0.1",
        port=args.port or int(os.getenv("POSTGRES_PORT") or "5432"),
        user=args.user or os.getenv("POSTGRES_USER") or "postgres",
        password=args.password
        if args.password is not None
        else os.getenv("POSTGRES_PASSWORD", ""),
        database=args.database or os.getenv("POSTGRES_DB") or "nexus",
        admin_database=args.admin_database,
    )


def main() -> int:
    args = parse_args()
    load_env(args.env_file)

    bootstrap_settings = make_settings(args)

    try:
        result = bootstrap_postgres_sync(bootstrap_settings)
    except Exception as exc:  # noqa: BLE001
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[bootstrap-db] failed: {exc}", file=sys.stderr)
        return 1

    payload = {"ok": True, **result}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        state = "created" if payload["database_created"] else "already exists"
        print(
            f"[bootstrap-db] database={payload['database']} ({state}), "
            f"applied {payload['schema_statements']} schema statements"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
