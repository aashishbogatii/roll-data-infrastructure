"""Shared APN and situs key normalization for ingest and lookup."""

from __future__ import annotations

import re

import pandas as pd

# Street suffix and directional long forms -> canonical abbreviation.
_SUFFIX = {
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "ROAD": "RD", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR",
    "PLACE": "PL", "TERRACE": "TER", "PARKWAY": "PKWY", "HIGHWAY": "HWY",
    "TRAIL": "TRL", "SQUARE": "SQ",
    "WY": "WAY", "BL": "BLVD", "BLV": "BLVD", "AV": "AVE",
}
_DIRECTIONAL = {
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
}
_TOKEN_MAP = {**_SUFFIX, **_DIRECTIONAL}


def _clean_component(value: object) -> str | None:
    """Strip to a non-empty string; None/NaN/NA/blank -> None."""
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    return s or None


def join_apn(*components: tuple[object, int]) -> str | None:
    """Zero-pad each (value, width) and dash-join; None if any missing."""
    cleaned = [(_clean_component(value), width) for value, width in components]
    if any(value is None for value, _ in cleaned):
        return None
    return "-".join(value.zfill(width) for value, width in cleaned)


def strip_apn(value: object) -> str | None:
    """APN match key: alphanumerics only, uppercased. None if empty."""
    key = re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()
    return key or None


def _zip5(value: object) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:5] if len(digits) >= 5 else (digits or None)


def normalize_situs(
    number: object,
    street: object,
    zip_code: object,
    *,
    city: object = None,
    state: object = None,
    sub: object = None,
) -> str | None:
    """Situs address, comma-delimited: '<num> <street>, <city>, <ST> <zip>'.

    Uppercased and street suffixes/directionals standardized, so it matches a
    normalized source address by comma-separated field (case-insensitive).
    None if no street.
    """
    raw_parts = [
        _clean_component(number),
        _clean_component(sub),
        _clean_component(street),
    ]
    line = " ".join(p for p in raw_parts if p).upper()
    line = re.sub(r"[^\w\s/]", " ", line)
    tokens = [_TOKEN_MAP.get(tok, tok) for tok in line.split()]

    if not tokens:
        return None

    fields = [" ".join(tokens)]

    city_clean = _clean_component(city)
    if city_clean:
        city_norm = " ".join(re.sub(r"[^\w\s]", " ", city_clean.upper()).split())
        if city_norm:
            fields.append(city_norm)

    st = _clean_component(state)
    z = _zip5(zip_code)
    tail = " ".join(x for x in (st.upper() if st else None, z) if x)
    if tail:
        fields.append(tail)

    return ", ".join(fields)
