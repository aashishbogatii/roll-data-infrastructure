"""Vectorized column transforms: coerce a raw text column to a typed Series."""

from __future__ import annotations

import pandas as pd


def col_str(s: pd.Series) -> pd.Series:
    """Strip; empty -> NA."""
    out = s.astype("string").str.strip()
    return out.mask(out == "", pd.NA)


def col_title(s: pd.Series) -> pd.Series:
    """Strip + title-case; empty -> NA. For names/addresses, not codes."""
    return col_str(s).str.title()


def col_numstr(s: pd.Series) -> pd.Series:
    """Numeric-ish code -> string, dropping a trailing '.0' ('20.0' -> '20')."""
    out = s.astype("string").str.strip()
    out = out.str.replace(r"\.0$", "", regex=True)
    return out.mask(out == "", pd.NA)


def col_int(s: pd.Series) -> pd.Series:
    """Whole-number -> nullable Int64; bad/blank -> NA (0 is kept)."""
    cleaned = (
        s.astype("string").str.replace(",", "", regex=False).str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce").astype("Int64")


def col_float(s: pd.Series) -> pd.Series:
    """Real number -> nullable Float64; bad/blank -> NA (for .5 baths, acres)."""
    cleaned = (
        s.astype("string").str.replace(",", "", regex=False).str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce").astype("Float64")


def col_yyyymmdd(s: pd.Series) -> pd.Series:
    """Parse a 20140515-style column -> datetime64."""
    digits = (
        pd.to_numeric(s, errors="coerce").astype("Int64").astype("string")
    )
    return pd.to_datetime(digits, format="%Y%m%d", errors="coerce")


def col_date(s: pd.Series) -> pd.Series:
    """Parse a datetime/ISO-string column -> datetime64."""
    return pd.to_datetime(s, errors="coerce")
