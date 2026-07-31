"""Enrich a cleaned roll with parcel geometry and building characteristics, by APN."""

from __future__ import annotations

import pandas as pd
import shapely

_GEOMETRY_COLUMNS = ["apn", "longitude", "latitude", "geometry"]


def enrich_geometry(
    df: pd.DataFrame, source_path: str, *, key: str = "apn_normalized"
) -> pd.DataFrame:
    """LEFT JOIN longitude/latitude/geometry from a parcel parquet by APN
    (WKB geometry -> GeoJSON)."""
    parcels = (
        pd.read_parquet(source_path, columns=_GEOMETRY_COLUMNS)
        .drop_duplicates("apn")
        .rename(columns={"apn": key})
    )

    parcels["geometry"] = shapely.to_geojson(
        shapely.from_wkb(parcels["geometry"].to_numpy())
    )
    return df.merge(parcels, on=key, how="left")


def _left_join_by_apn(
    df: pd.DataFrame, other: pd.DataFrame, key: str
) -> pd.DataFrame:
    """LEFT JOIN `other` onto the roll by APN, adding only columns the roll does
    not already have (so an enrichment never overwrites a roll field)."""
    other = other.drop_duplicates(key)
    cols = [c for c in other.columns if c == key or c not in df.columns]
    return df.merge(other[cols], on=key, how="left")


def enrich_characteristics(
    df: pd.DataFrame, characteristics: pd.DataFrame, *, key: str = "apn_normalized"
) -> pd.DataFrame:
    """LEFT JOIN cleaned building characteristics onto the roll by APN."""
    return _left_join_by_apn(df, characteristics, key)


def enrich_transfers(
    df: pd.DataFrame, transfers: pd.DataFrame, *, key: str = "apn_normalized"
) -> pd.DataFrame:
    """LEFT JOIN each parcel's most recent recorded sale onto the roll by APN.

    Only a few percent of parcels change hands inside the two-year transfer
    window, so the sale columns are null for most of the roll. That is the
    expected shape, not a failed join. The transfers transform has already
    reduced to one sale per parcel, so the dedup here is only a safety net.
    """
    return _left_join_by_apn(df, transfers, key)
