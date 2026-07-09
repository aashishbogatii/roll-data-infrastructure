"""Sacramento UNSECURED roll transform: raw xlsx -> cleaned DataFrame."""

from __future__ import annotations

import pandas as pd

from ..normalize import join_apn, normalize_situs, strip_apn
from ..parsers import col_int, col_numstr, col_str, col_title

COUNTY = "sacramento"
ROLL_TYPE = "unsecured"

EXPECTED_COLUMNS = (
    "MAPB", "PG", "PCL", "PSUB", "PARSU", "CLASS_CODE", "TRA",
    "SITUS_ST_NUMB", "SITUS_PRE_DIR", "SITUS_STREET", "SITUS_SUFFIX",
    "SITUS_POST_DIR", "SITUS_UNIT_IND", "SITUS_UNIT_NUMB", "SITUS_CITY",
    "SITUS_STATE", "SITUS_ZIP", "DBA_NAME", "CARE_OF", "MAIL_ST_NUMB",
    "MAIL_PRE_DIR", "MAIL_STREET", "MAIL_POST_DIR", "MAIL_SUFFIX",
    "MAIL_UNIT_IND", "MAIL_UNIT_NUMB", "MAIL_CITY", "MAIL_STATE", "MAIL_ZIP",
    "MAIL_PO_BOX", "FOREIGN_ADD1", "FOREIGN_ADD2", "FOREIGN_ADD3",
    "CHURCH_EX", "VET_EX", "HO_EX", "LAND_VALUE", "IMP_VALUE", "FIXT_VALUE",
    "PPROP_VALUE", "BOAT_VALUE", "ACFT_VALUE", "BOAT_NUM", "ACFT_NUM",
    "IS_SECURED",
)

MONEY_COLUMNS = (
    "land_value", "improvement_value", "fixture_value",
    "personal_property_value", "boat_value", "aircraft_value",
    "total_assessed_value", "homeowner_exemption",
    "church_exemption", "vet_exemption",
)

# target <- (source column, vectorized transform). Keys/composites in clean().
FIELD_MAP = {
    "tax_rate_area": ("TRA", col_str),
    "class_code": ("CLASS_CODE", col_numstr),
    "land_value": ("LAND_VALUE", col_int),
    "improvement_value": ("IMP_VALUE", col_int),
    "fixture_value": ("FIXT_VALUE", col_int),
    "personal_property_value": ("PPROP_VALUE", col_int),
    "boat_value": ("BOAT_VALUE", col_int),
    "aircraft_value": ("ACFT_VALUE", col_int),
    "homeowner_exemption": ("HO_EX", col_int),
    "church_exemption": ("CHURCH_EX", col_int),
    "vet_exemption": ("VET_EX", col_int),
    "dba_name": ("DBA_NAME", col_title),
    "care_of": ("CARE_OF", col_title),
    "situs_number": ("SITUS_ST_NUMB", col_numstr),
    "situs_city": ("SITUS_CITY", col_title),
    "situs_state": ("SITUS_STATE", col_str),
    "situs_zip": ("SITUS_ZIP", col_numstr),
    "mail_city": ("MAIL_CITY", col_title),
    "mail_state": ("MAIL_STATE", col_str),
    "mail_zip": ("MAIL_ZIP", col_numstr),
    "mail_po_box": ("MAIL_PO_BOX", col_numstr),
    "boat_number": ("BOAT_NUM", col_str),
    "aircraft_number": ("ACFT_NUM", col_str),
    "is_secured": ("IS_SECURED", col_numstr),
    "parsu": ("PARSU", col_str),
    "mapb": ("MAPB", col_str),
    "pg": ("PG", col_str),
    "pcl": ("PCL", col_str),
    "psub": ("PSUB", col_str),
}

_TOTAL_PARTS = (
    "land_value", "improvement_value", "fixture_value",
    "personal_property_value", "boat_value", "aircraft_value",
)


def _clean(v: object) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return None if not s or s.lower() in {"nan", "none", "<na>", "nat"} else s


def _numstr(v: object) -> str | None:
    """Numeric-ish value -> string without trailing '.0' ('221.0' -> '221')."""
    s = _clean(v)
    if s is None:
        return None
    try:
        f = float(s)
    except ValueError:
        return s
    return str(int(f)) if f.is_integer() else s


def _words(*vals: object) -> str | None:
    """Join non-empty parts with single spaces."""
    return " ".join(p for p in (_clean(v) for v in vals) if p) or None


def clean(df: pd.DataFrame, *, roll_year: int) -> pd.DataFrame:
    """Raw Sacramento unsecured xlsx (read dtype=str) -> cleaned DataFrame."""
    df = df.rename(columns=lambda c: str(c).strip())
    
    keep = [c for c in df.columns if c and not c.startswith("Unnamed")]
    df = df.loc[:, keep]
    if tuple(df.columns) != EXPECTED_COLUMNS:
        raise ValueError(
            "Sacramento unsecured header drift: columns != EXPECTED_COLUMNS"
        )

    out = pd.DataFrame(index=df.index)
    for target, (src, transform) in FIELD_MAP.items():
        out[target] = transform(df[src])

    out["county"] = COUNTY
    out["roll_type"] = ROLL_TYPE
    out["roll_year"] = roll_year
    out["assessment_year"] = roll_year  # no value date on unsecured

    out["apn"] = [
        join_apn((mapb, 3), (pg, 4), (pcl, 3), (psub, 4), (parsu, 4))
        for mapb, pg, pcl, psub, parsu in zip(
            df["MAPB"], df["PG"], df["PCL"], df["PSUB"], df["PARSU"]
        )
    ]
    out["apn_normalized"] = [strip_apn(apn) for apn in out["apn"]]

    # Situs street assembled from the granular parts (pre/street/suffix/post).
    streets = [
        _words(pre, st, suf, post)
        for pre, st, suf, post in zip(
            df["SITUS_PRE_DIR"], df["SITUS_STREET"],
            df["SITUS_SUFFIX"], df["SITUS_POST_DIR"],
        )
    ]
    out["situs_street"] = [s.title() if s else None for s in streets]
    out["situs_unit"] = [
        _words(ind, num)
        for ind, num in zip(df["SITUS_UNIT_IND"], df["SITUS_UNIT_NUMB"])
    ]
    out["address"] = [
        normalize_situs(_numstr(num), street, z, city=c, state=st)
        for num, street, z, c, st in zip(
            df["SITUS_ST_NUMB"], streets, df["SITUS_ZIP"],
            df["SITUS_CITY"], df["SITUS_STATE"],
        )
    ]

    mail = [
        _words(_numstr(n), pre, st, post, suf, ind, num)
        for n, pre, st, post, suf, ind, num in zip(
            df["MAIL_ST_NUMB"], df["MAIL_PRE_DIR"], df["MAIL_STREET"],
            df["MAIL_POST_DIR"], df["MAIL_SUFFIX"],
            df["MAIL_UNIT_IND"], df["MAIL_UNIT_NUMB"],
        )
    ]
    out["mail_address"] = [m.title() if m else None for m in mail]

    out["total_assessed_value"] = (
        out[list(_TOTAL_PARTS)].sum(axis=1, min_count=1).astype("Int64")
    )
    return out


def validate(df: pd.DataFrame) -> None:
    """Raise ValueError if keys are missing or money is negative."""
    errors: list[str] = []
    if df["apn"].isna().any():
        errors.append(f"{int(df['apn'].isna().sum())} rows missing apn")
    if df["county"].isna().any():
        errors.append(f"{int(df['county'].isna().sum())} rows missing county")
    for col in MONEY_COLUMNS:
        bad = int((df[col] < 0).sum())
        if bad:
            errors.append(f"{bad} rows have negative {col}")
    if errors:
        raise ValueError("Validation failed: " + "; ".join(errors))
