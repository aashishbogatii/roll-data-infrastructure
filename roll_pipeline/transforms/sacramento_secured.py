"""Sacramento SECURED roll transform: raw xlsx -> cleaned, typed DataFrame."""

from __future__ import annotations

import pandas as pd

from ..normalize import join_apn, normalize_situs, strip_apn
from ..parsers import col_date, col_int, col_str, col_title

COUNTY = "sacramento"
ROLL_TYPE = "secured"

EXPECTED_COLUMNS = (
    "MAPB", "PG", "PCL", "PSUB", "TAX_RATE_AREA",
    "SITUS_NUMBER", "SITUS_CITY", "SITUS_STREET", "SITUS_ZIP",
    "OWNER_CODE", "OWNER", "MAIL_ADDRESS", "MAIL_CITY", "MAIL_STATE",
    "MAIL_ZIP", "CARE_OF", "ZONING", "LAND_USE_CODE", "RECORDING_DATE",
    "RECORDING_PAGE", "DEED_TYPE", "LAND", "IM", "FIXTURE", "PP",
    "HO_EX", "EX", "VALUE_DT", "NGH", "ACTION_CODE",
)

MONEY_COLUMNS = (
    "land_value", "improvement_value", "total_assessed_value",
    "fixture_value", "personal_property_value",
    "homeowner_exemption", "other_exemption",
)

# target <- (source column, vectorized transform). Keys/composites in clean().
FIELD_MAP = {
    "land_value": ("LAND", col_int),
    "improvement_value": ("IM", col_int),
    "fixture_value": ("FIXTURE", col_int),
    "personal_property_value": ("PP", col_int),
    "homeowner_exemption": ("HO_EX", col_int),
    "other_exemption": ("EX", col_int),
    "value_date": ("VALUE_DT", col_date),
    "tax_rate_area": ("TAX_RATE_AREA", col_str),
    "zoning": ("ZONING", col_str),
    "land_use_code": ("LAND_USE_CODE", col_str),
    "neighborhood": ("NGH", col_str),
    "owner_name": ("OWNER", col_title),
    "owner_code": ("OWNER_CODE", col_str),
    "care_of": ("CARE_OF", col_title),
    "mail_address": ("MAIL_ADDRESS", col_title),
    "mail_city": ("MAIL_CITY", col_title),
    "mail_state": ("MAIL_STATE", col_str),
    "mail_zip": ("MAIL_ZIP", col_str),
    "last_ownership_transfer_date": ("RECORDING_DATE", col_date),
    "recording_page": ("RECORDING_PAGE", col_str),
    "deed_type": ("DEED_TYPE", col_str),
    "situs_number": ("SITUS_NUMBER", col_str),
    "situs_street": ("SITUS_STREET", col_title),
    "situs_city": ("SITUS_CITY", col_title),
    "situs_zip": ("SITUS_ZIP", col_str),
    "mapb": ("MAPB", col_str),
    "pg": ("PG", col_str),
    "pcl": ("PCL", col_str),
    "psub": ("PSUB", col_str),
    "action_code": ("ACTION_CODE", col_str),
}


_TOTAL_PARTS = (
    "land_value", "improvement_value",
    "fixture_value", "personal_property_value",
)

COLUMN_ORDER = (
    # identity & keys
    "county", "roll_year", "roll_type", "apn", "apn_normalized",
    "mapb", "pg", "pcl", "psub",
    # situs
    "address", "situs_number", "situs_street", "situs_city", "situs_zip",
    # valuation
    "land_value", "improvement_value", "fixture_value",
    "personal_property_value", "total_assessed_value", "assessment_year",
    "value_date",
    # exemptions
    "homeowner_exemption", "other_exemption",
    # tax
    "tax_rate_area",
    # classification
    "zoning", "land_use_code", "neighborhood",
    # ownership
    "owner_name", "owner_code", "care_of",
    # mailing
    "mail_address", "mail_city", "mail_state", "mail_zip",
    # recording / transfer
    "last_ownership_transfer_date", "recording_page", "deed_type",
    "action_code",
    # parcel dataset enrichment
    "lot_size", "parcel_type", "geometry",
)


def clean(df: pd.DataFrame, *, roll_year: int) -> pd.DataFrame:
    """Raw Sacramento secured xlsx (read dtype=str) -> cleaned DataFrame."""
    df = df.rename(columns=lambda c: str(c).strip())  # padded ACTION_CODE
    if tuple(df.columns) != EXPECTED_COLUMNS:
        raise ValueError(
            "Sacramento secured header drift: columns != EXPECTED_COLUMNS"
        )

    out = pd.DataFrame(index=df.index)
    for target, (src, transform) in FIELD_MAP.items():
        out[target] = transform(df[src])

    out["county"] = COUNTY
    out["roll_type"] = ROLL_TYPE
    out["roll_year"] = roll_year
    out["apn"] = [
        join_apn((mapb, 3), (pg, 4), (pcl, 3), (psub, 4))
        for mapb, pg, pcl, psub in zip(
            df["MAPB"], df["PG"], df["PCL"], df["PSUB"]
        )
    ]
    out["apn_normalized"] = [strip_apn(apn) for apn in out["apn"]]
    out["address"] = [
        normalize_situs(n, s, z, city=c, state="CA")
        for n, s, c, z in zip(
            df["SITUS_NUMBER"], df["SITUS_STREET"],
            df["SITUS_CITY"], df["SITUS_ZIP"],
        )
    ]
    out["total_assessed_value"] = (
        out[list(_TOTAL_PARTS)].sum(axis=1, min_count=1).astype("Int64")
    )
    out["assessment_year"] = (
        out["value_date"].dt.year.fillna(roll_year).astype("Int64")
    )
    cols = [c for c in COLUMN_ORDER if c in out.columns]
    cols += [c for c in out.columns if c not in COLUMN_ORDER]
    return out[cols]


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
