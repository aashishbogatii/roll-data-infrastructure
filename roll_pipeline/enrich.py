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


def enrich_characteristics(
    df: pd.DataFrame, characteristics: pd.DataFrame, *, key: str = "apn_normalized"
) -> pd.DataFrame:
    """LEFT JOIN cleaned building characteristics onto the roll by APN, adding
    only columns not already on the roll (never overwrites roll fields)."""
    characteristics = characteristics.drop_duplicates(key)
    cols = [c for c in characteristics.columns if c == key or c not in df.columns]
    return df.merge(characteristics[cols], on=key, how="left")
