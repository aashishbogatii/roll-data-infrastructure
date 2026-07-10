"""Golden tests: real-shaped raw rows -> expected cleaned output. Locks the
source->target mapping and the derived columns."""

import pandas as pd
import pytest

from roll_pipeline.transforms import sacramento_characteristics as C
from roll_pipeline.transforms import sacramento_secured as S
from roll_pipeline.transforms import sacramento_unsecured as U

# every raw column C.clean() reads: the FIELD_MAP sources + PARCEL_NUMBER
_CHAR_COLUMNS = [src for src, _ in C.FIELD_MAP.values()] + list(C._DERIVED_SOURCES)


def _raw(columns, **vals):
    """One-row DataFrame with every expected column (defaults to '')."""
    return pd.DataFrame([{c: vals.get(c, "") for c in columns}])


def test_secured_golden_row():
    df = _raw(
        S.EXPECTED_COLUMNS,
        MAPB="001", PG="0011", PCL="001", PSUB="0000",
        TAX_RATE_AREA="03169",
        SITUS_NUMBER="221", SITUS_CITY="SACRAMENTO",
        SITUS_STREET="JIBBOOM ST", SITUS_ZIP="95811",
        OWNER="PATEL TAYJES", ZONING="C-2-SPD",
        LAND="490338", IM="612928", FIXTURE="0", PP="0",
        HO_EX="0", EX="0", VALUE_DT="2014-05-15", RECORDING_DATE="20140515",
    )
    out = S.clean(df, roll_year=2025)
    S.validate(out)
    r = out.iloc[0]

    assert r["county"] == "sacramento"
    assert r["roll_type"] == "secured"
    assert r["apn"] == "001-0011-001-0000"
    assert r["apn_normalized"] == "00100110010000"
    assert r["address"] == "221 JIBBOOM ST, SACRAMENTO, CA 95811"
    assert r["land_value"] == 490338
    assert str(out["land_value"].dtype) == "Int64"
    assert r["total_assessed_value"] == 1103266      # 490338 + 612928
    assert r["tax_rate_area"] == "03169"             # leading zero kept
    assert r["owner_name"] == "Patel Tayjes"         # title-cased
    assert r["assessment_year"] == 2014              # from value_date


def test_secured_header_drift_raises():
    with pytest.raises(ValueError, match="header drift"):
        S.clean(pd.DataFrame([{"WRONG": "x"}]), roll_year=2025)


def test_unsecured_golden_row():
    df = _raw(
        U.EXPECTED_COLUMNS,
        MAPB="001", PG="0011", PCL="001", PSUB="0000", PARSU="0002",
        CLASS_CODE="20.0", TRA="03169",
        SITUS_ST_NUMB="221.0", SITUS_STREET="JIBBOOM", SITUS_SUFFIX="ST",
        SITUS_CITY="SACRAMENTO", SITUS_STATE="CA", SITUS_ZIP="95811.0",
        DBA_NAME="CROSS ROADS INN", CARE_OF="PATEL TAYJES",
        LAND_VALUE="0", IMP_VALUE="0", FIXT_VALUE="0",
        PPROP_VALUE="462", BOAT_VALUE="0", ACFT_VALUE="0",
        HO_EX="0", CHURCH_EX="0", VET_EX="0", IS_SECURED="0",
    )
    out = U.clean(df, roll_year=2025)
    U.validate(out)
    r = out.iloc[0]

    assert r["roll_type"] == "unsecured"
    assert r["apn"] == "001-0011-001-0000-0002"
    assert r["apn_normalized"] == "001001100100000002"
    assert len(r["apn_normalized"]) == 18            # distinct from secured's 14
    assert r["address"] == "221 JIBBOOM ST, SACRAMENTO, CA 95811"
    assert r["situs_street"] == "Jibboom St"         # assembled from parts
    assert r["class_code"] == "20"                   # '.0' stripped
    assert r["situs_number"] == "221"                # '.0' stripped
    assert r["dba_name"] == "Cross Roads Inn"
    assert r["personal_property_value"] == 462
    assert r["total_assessed_value"] == 462          # incl. boats/aircraft (0)
    assert r["assessment_year"] == 2025              # = roll_year (no value date)


def test_unsecured_drops_trailing_unnamed_column():
    # the real xlsx has an empty 46th column; clean() must drop it, not error
    df = _raw(U.EXPECTED_COLUMNS, MAPB="001", PG="0011", PCL="001",
              PSUB="0000", PARSU="0002")
    df["Unnamed: 45"] = ""
    out = U.clean(df, roll_year=2025)
    assert out.iloc[0]["apn"] == "001-0011-001-0000-0002"


def test_characteristics_golden_row():
    df = _raw(
        _CHAR_COLUMNS,
        PARCEL_NUMBER="00100400120000",
        QUALITY_CLASS="D50", CONDITION="Average",
        EFFECTIVE_YEAR="1998", NUMBER_OF_STORIES="1",
        ROOF_COVER="S", SLAB_FLOOR="Y", CENTRAL_AIR_CONDITIONING="Both",
        NUMBER_OF_BEDROOMS="3", NUMBER_OF_BATHROOMS="2.5",
        DINING_ROOM="1", UTILITY_ROOM="1", TOTAL_NUMBER_OF_ROOMS="6",
        SQUARE_FOOTAGE="6000", ACRES="0.14",
        FIRST_FLOOR_AREA="910", SECOND_FLOOR_AREA="0",
        FINISH_BASEMENT_AREA="194", AREA_4_MODIFICATION="1104",
        NUMBER_OF_PARKING_STALLS="2", POOL_DATE="1999",
        IRS_STAMP_AMOUNT="330", IRS_STAMP_CODE="F",
    )
    out = C.clean(df)
    C.validate(out)
    r = out.iloc[0]

    assert r["apn_normalized"] == "00100400120000"
    assert len(r["apn_normalized"]) == 14            # matches secured key width
    # numeric types preserved
    assert r["bedrooms"] == 3
    assert str(out["bedrooms"].dtype) == "Int64"
    assert r["bathrooms"] == 2.5                     # half-bath kept as float
    assert str(out["bathrooms"].dtype) == "Float64"
    assert r["lot_acres"] == 0.14
    assert r["total_living_sqft"] == 1104            # from AREA_4_MODIFICATION
    # raw codes kept as-is (no decoding)
    assert r["slab"] == "Y"
    assert r["heating_cooling"] == "Both"
    assert r["roof_cover"] == "S"
    assert r["quality_class"] == "D50"
    assert r["transfer_tax_code"] == "F"


def test_characteristics_missing_columns_raises():
    with pytest.raises(ValueError, match="missing columns"):
        C.clean(pd.DataFrame([{"PARCEL_NUMBER": "00100400120000"}]))