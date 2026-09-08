"""Sacramento SECURED roll transform: raw xlsx -> cleaned, typed DataFrame."""

from __future__ import annotations

import pandas as pd

from ..normalize import join_apn, normalize_situs, strip_apn
from ..parsers import col_date, col_int, col_str, col_title

COUNTY = "sacramento"
ROLL_TYPE = "secured"

# Land-use code -> description. Residential (A) by 3- then 2-char prefix,
# everything else by first-char major category.
_LAND_USE_RES3 = {  # A[1-4] + form/lot variant in the 3rd char
    "A1A": "Single Family Residence", "A1B": "Single Family Residence",
    "A1C": "Single Family Residence (Rural, <2 ac)",
    "A1D": "Single Family Residence (Rural, 2-5 ac)",
    "A1E": "Single Family Residence (Rural, >5 ac)",
    "A1F": "Condominium", "A1G": "Planned Unit Development",
    "A1H": "Row House", "A1J": "Half Plex",
    "A2A": "Two Family (2 Single Family)", "A2B": "Duplex",
    "A2X": "Condominium (Two Family)", "A2Y": "PUD (Two Family)",
    "A3A": "Three Family (3 Single Family)",
    "A3B": "Three Family (1 Single Family)", "A3C": "Triplex",
    "A4A": "Four Family (4 Single Family)",
    "A4B": "Four Family (1 SF + 1 Triplex)",
    "A4C": "Four Family (2 SF + 1 Duplex)",
    "A4D": "Four Family (2 Duplexes)", "A4E": "Fourplex",
}
_LAND_USE_RES2 = {  # residential types keyed by the first two chars
    "A1": "Single Family Residence", "A2": "Two Family",
    "A3": "Three Family", "A4": "Four Family",
    "AD": "Residential Conversion", "AE": "Low-rise Apartment",
    "AF": "High-rise Apartment", "AG": "Apartment Court (>4 units)",
    "AH": "Mobile Home Park", "AJ": "Hotel", "AK": "Boarding House",
    "AL": "Rooming House", "AM": "Sorority/Fraternity House", "AN": "Motel",
    "AQ": "Common Area (Condo/PUD)", "AR": "Bed & Breakfast Inn",
    "AT": "Mobile Home",
}
_LAND_USE_MAJOR = {  # first char -> general category (non-residential)
    "A": "Residential (Other)", "B": "Retail/Commercial", "C": "Office",
    "D": "Personal Care/Health", "E": "Church/Welfare", "F": "Recreational",
    "G": "Industrial", "H": "Agriculture", "I": "Vacant Land",
    "M": "Miscellaneous", "W": "Public/Utilities",
}


def _land_use_desc(code: object) -> str | None:
    """Decode a 6-char land-use code: residential in detail, else its category."""
    if code is None or pd.isna(code):
        return None
    c = str(code).strip().upper()
    if not c:
        return None
    return (
        _LAND_USE_RES3.get(c[:3])
        or _LAND_USE_RES2.get(c[:2])
        or _LAND_USE_MAJOR.get(c[:1])
    )


# Land-use prefixes by valuation approach: 1-4 unit residential -> cma;
# apartments/lodging and B/C/D/F/G commercial majors -> income. AD (residential
# conversion) is units-dependent, so it sits in the income set (units-checked:
# <=4 units -> cma, 5+ -> income).
_CMA_PREFIXES = frozenset({"A1", "A2", "A3", "A4", "AT"})
_INCOME_PREFIXES = frozenset({
    "AD", "AE", "AF", "AG", "AH", "AJ", "AK", "AL", "AM", "AN", "AR",
})
_INCOME_MAJORS = frozenset({"B", "C", "D", "F", "G"})
_SPECIAL_MAJORS = frozenset({"H", "E", "M", "W"})


def _code_units(code: object) -> int | None:
    """Unit count from code positions 3-5 ('AF047M' -> 47); non-digit/000 -> None."""
    if code is None or pd.isna(code):
        return None
    digits = str(code).strip()[2:5]
    if not digits.isdigit():
        return None
    return int(digits) or None


def _valuation_approach(code: object) -> str | None:
    """Route a parcel to cma / income / land / special from its land-use code."""
    if code is None or pd.isna(code):
        return None
    c = str(code).strip().upper()
    if not c:
        return None
    major, prefix = c[:1], c[:2]
    if major == "I":                                # vacant -> land comps
        return "land"
    if major in _SPECIAL_MAJORS or prefix == "AQ":  # ag/church/misc/common area
        return "special"
    if prefix in _CMA_PREFIXES:                     # 1-4 unit residential
        return "cma"
    if prefix in _INCOME_PREFIXES:
        units = _code_units(c)                      # a sub-5-unit building
        if units is not None and units <= 4:        # still trades on comps
            return "cma"
        return "income"
    if major in _INCOME_MAJORS:                     # retail/office/health/rec/ind
        return "income"
    return "special"


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
    "zoning", "land_use_code", "land_use_desc", "valuation_approach", "units",
    "neighborhood",
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
    out["land_use_desc"] = out["land_use_code"].map(_land_use_desc).astype("string")
    out["units"] = out["land_use_code"].map(_code_units).astype("Int64")
    out["valuation_approach"] = (
        out["land_use_code"].map(_valuation_approach).astype("string")
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
