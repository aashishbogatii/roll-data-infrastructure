"""Ingest roll sources listed in registry.yaml into parquet.

Usage:
    python -m roll_pipeline.runner
"""

from __future__ import annotations

import importlib
import logging
import pathlib
from types import ModuleType

import pandas as pd
import yaml

from .config import ENV, OUTPUT_ROOT, SOURCE_ROOT
from .writer import write_parquet

_REGISTRY = pathlib.Path(__file__).with_name("registry.yaml")

logger = logging.getLogger(__name__)


def _resolve(path: str) -> str:
    """Full path for a registry entry. Relative paths are joined to SOURCE_ROOT
    (local dir or s3://...); absolute local (C:/...) or s3:// paths are used
    unchanged -- so the same registry runs local or in cloud.
    """
    if "://" in path or path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        return path
    return f"{SOURCE_ROOT}/{path.lstrip('/')}"


def get_transform(name: str) -> ModuleType:
    """Import transforms/<name>.py; it must expose clean() and validate()."""
    try:
        module = importlib.import_module(f"{__package__}.transforms.{name}")
    except ModuleNotFoundError as e:
        raise ValueError(
            f"No transform module 'transforms/{name}.py' for {name!r}"
        ) from e
    for fn in ("clean", "validate"):
        if not hasattr(module, fn):
            raise ValueError(
                f"transforms/{name}.py is missing required function {fn}()"
            )
    return module


def load_sources(registry_path: pathlib.Path = _REGISTRY) -> list[dict]:
    data = yaml.safe_load(registry_path.read_text())
    return data.get("sources", [])


def _read_raw(entry: dict, path: str) -> pd.DataFrame:
    """Read the raw file at `path` as text (dtype=str) so codes keep leading
    zeros. Local xlsx use the fast calamine engine; s3:// falls back to the
    default engine, since calamine can't stream over s3fs."""
    fmt = entry["format"]
    if fmt == "xlsx":
  
        return pd.read_excel(
            path,
            sheet_name=entry.get("sheet", 0),
            dtype=str,
            engine="calamine",
        )
    if fmt == "csv":
        return pd.read_csv(path, dtype=str)
    raise ValueError(
        f"Unsupported format {fmt!r} for source {entry['name']!r}"
    )


def run_source(entry: dict, out_root: str) -> str:
    """Ingest one source end to end. Returns the written parquet path/URL."""
    name = entry["name"]
    transform = get_transform(entry["transform"])

    src = _resolve(entry["path"])
    logger.info("[%s] reading %s", name, src)
    raw = _read_raw(entry, src)
    logger.info("[%s] read %s raw rows", name, f"{len(raw):,}")

    df = transform.clean(raw, roll_year=entry["roll_year"])
    transform.validate(df)
    logger.info(
        "[%s] cleaned + validated -> %s rows, %d cols",
        name, f"{len(df):,}", len(df.columns),
    )

    if entry.get("parcels"):
        from .enrich import enrich_geometry

        parcels = _resolve(entry["parcels"])
        logger.info("[%s] enriching from %s", name, parcels)
        df = enrich_geometry(df, parcels)

    char = entry.get("characteristics")
    if char:
        from .enrich import enrich_characteristics

        char_src = _resolve(char["path"])
        logger.info("[%s] characteristics: reading %s", name, char_src)
        char_tf = get_transform(char["transform"])
        char_df = char_tf.clean(_read_raw(char, char_src))
        char_tf.validate(char_df)
        df = enrich_characteristics(df, char_df)
        matched = char_df["apn_normalized"].nunique()
        logger.info(
            "[%s] characteristics: joined %d fields for %s parcels",
            name, len(char_df.columns) - 1, f"{matched:,}",
        )

    dest = write_parquet(
        df,
        out_root,
        county=transform.COUNTY,
        roll_year=entry["roll_year"],
        basename=name,
    )
    logger.info("[%s] wrote %s rows -> %s", name, f"{len(df):,}", dest)
    return dest


def main(only: str | None = None) -> list[str]:
    """Ingest every registry source, or just `only` when a source name is given."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(module)s: %(message)s",
        force=True,
    )
    sources = load_sources()
    if only:
        sources = [s for s in sources if s["name"] == only]
        if not sources:
            raise SystemExit(f"No source named {only!r} in registry.yaml")
    logger.info(
        "ENV=%s | source=%s | output=%s | %d source(s)",
        ENV, SOURCE_ROOT, OUTPUT_ROOT, len(sources),
    )
    written = []
    for entry in sources:
        try:
            written.append(run_source(entry, OUTPUT_ROOT))
        except Exception:
            logger.exception("[%s] FAILED", entry["name"])
    logger.info("ingest complete: %d/%d source(s) ok", len(written), len(sources))
    return written


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else None)
