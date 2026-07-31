"""Sacramento two-year transfer list -> latest priced sale per parcel, by APN.

STAMP_CONV is the sale price (from transfer tax stamps), EVENT_DT the date.
"""

from __future__ import annotations

import pandas as pd

from ..normalize import strip_apn
from ..parsers import col_int, col_str, col_title

COUNTY = "sacramento"

EXPECTED_COLUMNS = (
    "PARCEL_NUMBER", "EVENT_DT", "EVENT_PG", "MULTI_PARCEL", "STAMP_CONV",
    "TAX_CODE", "ZONING", "USE_CODE", "NBR", "GRANTEE", "GRANTOR", "SITUS",
)

# tax was paid -> a price exists (NONE is an excluded gift/trust/death transfer)
_PRICED_TAX_CODES = frozenset({"FULL", "PART", "UNKN"})

# a literal 9 is a placeholder price on UNKN mobile-home transfers, not a price
_SENTINEL_PRICE = 9

# keep sales before the 2026 lien-date cutoff; a later resale is dropped so the
# kept sale reflects this roll year's value
_SALE_CUTOFF = pd.Timestamp("2026-01-15")


def col_yymmdd(s: pd.Series) -> pd.Series:
    """Parse the 6-digit YYMMDD event date ('260327' -> 2026-03-27)."""
    digits = s.astype("string").str.strip().str.zfill(6)
    return pd.to_datetime(digits, format="%y%m%d", errors="coerce")


FIELD_MAP = {
    ""
    "last_sale_date": ("EVENT_DT", col_yymmdd),
    "last_sale_price": ("STAMP_CONV", col_int),
    "last_sale_grantor": ("GRANTOR", col_title),
    "last_sale_grantee": ("GRANTEE", col_title),
}

COLUMN_ORDER = ("apn_normalized", *FIELD_MAP, "is_group_sale", "sale_group_id")


def clean(df: pd.DataFrame, **_: object) -> pd.DataFrame:
    """Raw transfer xlsx (read dtype=str) -> one priced sale per parcel."""
    df = df.rename(columns=lambda c: str(c).strip())
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Sacramento transfers: missing columns {missing}")

    # keep priced sales; group (multi-parcel) sales are flagged, not dropped, so
    # their bundled price can be filtered out downstream (is_group_sale = True).
    tax_code = df["TAX_CODE"].astype("string").str.strip().str.upper()
    df = df[tax_code.isin(_PRICED_TAX_CODES)]

    out = pd.DataFrame(index=df.index)
    out["apn_normalized"] = df["PARCEL_NUMBER"].map(strip_apn)
    for target, (src, transform) in FIELD_MAP.items():
        out[target] = transform(df[src])
    # MULTI_PARCEL counts ADDITIONAL parcels in the deal; > 0 = sold in a group
    is_group = pd.to_numeric(df["MULTI_PARCEL"], errors="coerce").gt(0)
    out["is_group_sale"] = is_group.astype("boolean")
    # date + recording page identify the deal; co-sold parcels share it
    grp = (df["EVENT_DT"].astype("string").str.strip()
           + df["EVENT_PG"].astype("string").str.strip())
    out["sale_group_id"] = col_str(grp.where(is_group))

    out = out[
        out["apn_normalized"].notna()
        & out["last_sale_price"].gt(_SENTINEL_PRICE)
        & out["last_sale_date"].lt(_SALE_CUTOFF)
    ]

    # one sale per parcel: prefer an individual sale over a group sale (whose
    # price is the bundled whole-deal amount), then the latest, then the higher
    # price on a same-day tie
    out = out.sort_values(
        ["is_group_sale", "last_sale_date", "last_sale_price"],
        ascending=[True, False, False],
    )
    out = out.drop_duplicates("apn_normalized", keep="first")
    # to date now that the datetime filter/sort/dedup are done
    out["last_sale_date"] = out["last_sale_date"].dt.date
    return out[list(COLUMN_ORDER)]


def validate(df: pd.DataFrame) -> None:
    """Raise if the join key is unusable or a sale is not a real, dated sale."""
    errors: list[str] = []
    if df["apn_normalized"].isna().any():
        errors.append(f"{int(df['apn_normalized'].isna().sum())} rows missing apn")

    if df["apn_normalized"].duplicated().any():
        errors.append("duplicate apn (want one sale per parcel)")

    if df["last_sale_date"].isna().any():
        errors.append(f"{int(df['last_sale_date'].isna().sum())} rows missing sale date")

    if (df["last_sale_price"] <= 0).any():
        errors.append(f"{int((df['last_sale_price'] <= 0).sum())} rows have a non-positive price")

    if (pd.to_datetime(df["last_sale_date"], errors="coerce") >= _SALE_CUTOFF).any():
        errors.append("sale on/after the lien cutoff")

    has_id = df["sale_group_id"].notna()
    grouped = df["is_group_sale"].fillna(False).astype(bool)
    if (has_id & ~grouped).any():
        errors.append("sale_group_id set on a non-group sale")
    if errors:
        raise ValueError("Validation failed: " + "; ".join(errors))
