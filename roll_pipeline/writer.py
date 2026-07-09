"""Write a cleaned DataFrame to out_root/<county>/<roll_year>/<basename>."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow

# Sort key + row-group size make point lookups prune to one row group instead
# of scanning the whole file (sorted key -> tight, non-overlapping group stats).
_SORT_KEY = "apn_normalized"
_ROW_GROUP_SIZE = 100_000


def write_parquet(
    df: pd.DataFrame,
    out_root: str,
    *,
    county: str,
    roll_year: int,
    basename: str,
) -> str:
    """Write df to <out_root>/<county>/<roll_year>/<basename>.parquet.

    Sorted by apn_normalized and written in ~100k-row row groups so a keyed
    lookup reads one group, not the whole file.
    """
    if _SORT_KEY in df.columns:
        df = df.sort_values(_SORT_KEY, kind="stable").reset_index(drop=True)
    dest_dir = f"{out_root.rstrip('/')}/{county}/{roll_year}"
    if not out_root.startswith("s3://"):
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
    path = f"{dest_dir}/{basename}.parquet"
    df.to_parquet(path, index=False, row_group_size=_ROW_GROUP_SIZE)
    return path
