"""AWS Lambda entrypoint for the roll ingest pipeline.
"""

from __future__ import annotations

from .config import OUTPUT_ROOT
from .runner import main as _run


def handler(event: dict | None = None, context: object = None) -> dict:
    """Lambda handler: ingest every registry source into parquet, or just the one
    named in event["source"]. Returns the curated location and written URLs."""
    only = (event or {}).get("source")
    written = _run(only)
    return {
        "statusCode": 200 if written else 500,
        "curated": OUTPUT_ROOT,
        "written": written,
    }