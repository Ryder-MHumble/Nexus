#!/usr/bin/env python3
"""Generate the checked-in OpenAPI schema from the live FastAPI app."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def generate_openapi(output_path: Path) -> Path:
    from app.main import app

    schema = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("openapi.json"),
        help="OpenAPI output path (default: openapi.json)",
    )
    args = parser.parse_args()

    output_path = generate_openapi(args.output)
    print(f"OpenAPI schema written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
