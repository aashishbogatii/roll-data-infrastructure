"""Enrich a cleaned roll with county parcel attributes joined by normalized APN."""

from __future__ import annotations

import pandas as pd
import shapely

_COLUMNS = ["apn", "longitude", "latitude", "geometry"]


def enrich_by_apn(
    df: pd.DataFrame, source_path: str, *, key: str = "apn_normalized"
) -> pd.DataFrame:
    """LEFT JOIN longitude/latitude/geometry from a parcel parquet by APN.
    """
    parcels = (
        pd.read_parquet(source_path, columns=_COLUMNS)
        .drop_duplicates("apn")
        .rename(columns={"apn": key})
    )

    parcels["geometry"] = shapely.to_geojson(
        shapely.from_wkb(parcels["geometry"].to_numpy())
    )
    return df.merge(parcels, on=key, how="left")
