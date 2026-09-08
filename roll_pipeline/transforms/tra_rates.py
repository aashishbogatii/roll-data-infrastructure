"""County TRA rate table -> total tax rate + its components, by tax rate area.

Shared by Sacramento and Placer; Placer's csv is built from its published PDF
by scripts/placer_tra_rates_from_pdf.py.
"""

from __future__ import annotations

import json

import pandas as pd

from ..parsers import col_float

EXPECTED_COLUMNS = (
    "county", "fiscal_year", "tra", "total_rate_pct", "is_unitary", "components",
)

COLUMN_ORDER = ("tax_rate_area", "total_tax_rate_pct", "tax_rate_components")


def _tra_key(s: pd.Series) -> pd.Series:
    """TRA join key: digits only ('54-319' -> '54319')."""
    return s.astype("string").str.replace(r"[^0-9]", "", regex=True)


def _components_json(value: object) -> str | None:
    """'*A=1.0000; B=0.0208' -> JSON [{name, rate_pct}, ...].

    The '*' marking the general Prop-13 levy is dropped: it is the countywide 1%
    on every TRA but a handful of utility ones, so it carries nothing per levy.
    """
    if value is None or pd.isna(value):
        return None
    levies = []
    for chunk in str(value).split(";"):
        name, sep, rate = chunk.strip().rpartition("=")
        if not sep:
            continue
        try:
            rate_pct = float(rate)
        except ValueError:
            continue
        levies.append({
            "name": name.strip().lstrip("*").strip(),
            "rate_pct": rate_pct,
        })
    return json.dumps(levies) if levies else None


def clean(df: pd.DataFrame, **_: object) -> pd.DataFrame:
    """Raw TRA rate csv (read dtype=str) -> one row per tax rate area."""
    df = df.rename(columns=lambda c: str(c).strip())
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"TRA rates: missing columns {missing}")

    out = pd.DataFrame(index=df.index)
    out["tax_rate_area"] = _tra_key(df["tra"])
    # the source column keeps the county's name; the output is explicit
    out["total_tax_rate_pct"] = col_float(df["total_rate_pct"])
    out["tax_rate_components"] = df["components"].map(_components_json)

    out = out[out["tax_rate_area"].str.len().gt(0)]
    # one rate per TRA; keep the first if the source repeats one
    return out.drop_duplicates("tax_rate_area")[list(COLUMN_ORDER)]


def validate(df: pd.DataFrame) -> None:
    """Raise if the join key is unusable, a rate is missing, or the components
    do not add up to the total rate."""
    errors: list[str] = []
    if df["tax_rate_area"].isna().any():
        errors.append("null tax_rate_area")
    if df["tax_rate_area"].duplicated().any():
        errors.append("duplicate tax_rate_area (want one rate per TRA)")
    rate = df["total_tax_rate_pct"]
    if rate.isna().any():
        errors.append(f"{int(rate.isna().sum())} rows missing rate")

    # A few Sacramento TRAs ship an incomplete component list, so only fail on a
    # widespread mismatch -> a broken parse, not a source gap.
    summed = df["tax_rate_components"].map(
        lambda j: sum(x["rate_pct"] for x in json.loads(j)) if j else None
    )
    off = (summed - rate).abs().gt(0.0001)
    if off.mean() > 0.01:
        errors.append(
            f"{int(off.sum())} of {len(df)} rows where components != the total"
        )

    if errors:
        raise ValueError("Validation failed: " + "; ".join(errors))
