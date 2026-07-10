"""Sacramento CHARACTERISTICS: raw xlsx -> building detail columns by APN.

Not a standalone roll source: clean() returns apn_normalized plus only the
building characteristics fields that are NOT already in the secured roll,
for an in-memory LEFT join in the runner (see enrich.enrich_characteristics).
No COUNTY/ROLL_TYPE stamping and no write step -- roll duplicates are omitted.
"""

from __future__ import annotations

import pandas as pd

from ..normalize import strip_apn
from ..parsers import col_float, col_int, col_str


FIELD_MAP = {
    "quality_class": ("QUALITY_CLASS", col_str),
    "condition": ("CONDITION", col_str),
    "effective_year": ("EFFECTIVE_YEAR", col_int),
    "stories": ("NUMBER_OF_STORIES", col_int),
    "roof_cover": ("ROOF_COVER", col_str),
    "slab": ("SLAB_FLOOR", col_str),
    "heating_cooling": ("CENTRAL_AIR_CONDITIONING", col_str),
    "bedrooms": ("NUMBER_OF_BEDROOMS", col_int),
    "bathrooms": ("NUMBER_OF_BATHROOMS", col_float),
    "dining_rooms": ("DINING_ROOM", col_int),
    "utility_rooms": ("UTILITY_ROOM", col_int),
    "supplemental_rooms": ("SUPPLEMENTAL_ROOMS", col_int),
    "total_rooms": ("TOTAL_NUMBER_OF_ROOMS", col_float),
    "lot_sqft": ("SQUARE_FOOTAGE", col_int),
    "lot_acres": ("ACRES", col_float),
    "first_floor_sqft": ("FIRST_FLOOR_AREA", col_int),
    "second_floor_sqft": ("SECOND_FLOOR_AREA", col_int),
    "basement_sqft": ("FINISH_BASEMENT_AREA", col_int),
    "garage_sqft": ("GARAGE_AREA", col_int),
    "converted_garage_sqft": ("CONVERTED_GARAGE_AREA", col_int),
    "total_addition_sqft": ("TOTAL_ADDITION_AREA", col_int),
    "total_living_sqft": ("AREA_4_MODIFICATION", col_int),
    "garage": ("NUMBER_OF_PARKING_STALLS", col_int),
    "pool_year": ("POOL_DATE", col_int),
    "transfer_tax_amount": ("IRS_STAMP_AMOUNT", col_int),
    "transfer_tax_code": ("IRS_STAMP_CODE", col_str),
}

_DERIVED_SOURCES = ("PARCEL_NUMBER",)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Raw characteristics -> apn_normalized + new fields"""
    needed = {src for src, _ in FIELD_MAP.values()} | set(_DERIVED_SOURCES)
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(
            f"Sacramento characteristics missing columns: {sorted(missing)}"
        )

    out = pd.DataFrame(index=df.index)

    out["apn_normalized"] = df["PARCEL_NUMBER"].map(strip_apn)

    for target, (src, transform) in FIELD_MAP.items():
        out[target] = transform(df[src])
    
    out = out[out["apn_normalized"].notna()]
    return out.drop_duplicates("apn_normalized")


def validate(df: pd.DataFrame) -> None:
    if "apn_normalized" not in df.columns or df["apn_normalized"].isna().all():
        raise ValueError(
            "characteristics: apn_normalized missing/empty after clean()"
        )
