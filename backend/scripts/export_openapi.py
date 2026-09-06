"""Dump the OpenAPI schema to openapi.json.

Handy for generating typed client SDKs (openapi-typescript, orval, etc.)
or committing the contract for review.

    uv run python scripts/export_openapi.py            # -> openapi.json
    uv run python scripts/export_openapi.py out.json   # custom path
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    paths = len(app.openapi()["paths"])
    print(f"wrote {out} ({paths} paths)")


if __name__ == "__main__":
    main()
