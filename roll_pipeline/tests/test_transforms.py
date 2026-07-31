"""Golden tests: real-shaped raw rows -> expected cleaned output. Locks the
source->target mapping and the derived columns."""

import pandas as pd
import pytest

from roll_pipeline.transforms import placer_secured as PL
from roll_pipeline.transforms import sacramento_characteristics as C
from roll_pipeline.transforms import sacramento_secured as S
from roll_pipeline.transforms import sacramento_transfers as T
from roll_pipeline.transforms import sacramento_unsecured as U

# every raw column C.clean() reads: the FIELD_MAP sources + PARCEL_NUMBER
_CHAR_COLUMNS = [src for src, _ in C.FIELD_MAP.values()] + list(C._DERIVED_SOURCES)


def _raw(columns, **vals):
    """One-row DataFrame with every expected column (defaults to '')."""
    return pd.DataFrame([{c: vals.get(c, "") for c in columns}])


# secured roll: raw row -> keys, normalized address, totals, value_date
def test_sacramento_secured_golden_row():
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
    assert r["total_assessed_value"] == 1103266
    assert r["tax_rate_area"] == "03169"
    assert r["owner_name"] == "Patel Tayjes"
    assert r["value_date"].year == 2014


# secured: a wrong header layout is rejected
def test_sacramento_secured_header_drift_raises():
    with pytest.raises(ValueError, match="header drift"):
        S.clean(pd.DataFrame([{"WRONG": "x"}]), roll_year=2025)


# unsecured roll: raw row -> keys, address assembled from parts, values
def test_sacramento_unsecured_golden_row():
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
    assert len(r["apn_normalized"]) == 18
    assert r["address"] == "221 JIBBOOM ST, SACRAMENTO, CA 95811"
    assert r["situs_street"] == "Jibboom St"
    assert r["class_code"] == "20"
    assert r["situs_number"] == "221"
    assert r["dba_name"] == "Cross Roads Inn"
    assert r["personal_property_value"] == 462
    assert r["total_assessed_value"] == 462
    assert r["assessment_year"] == 2025


# unsecured: the trailing empty xlsx column is dropped, not an error
def test_sacramento_unsecured_drops_trailing_unnamed_column():
    df = _raw(U.EXPECTED_COLUMNS, MAPB="001", PG="0011", PCL="001",
              PSUB="0000", PARSU="0002")
    df["Unnamed: 45"] = ""
    out = U.clean(df, roll_year=2025)
    assert out.iloc[0]["apn"] == "001-0011-001-0000-0002"


# characteristics: raw row -> typed building fields; raw codes kept as-is
def test_sacramento_characteristics_golden_row():
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
    assert len(r["apn_normalized"]) == 14
    assert r["bedrooms"] == 3
    assert str(out["bedrooms"].dtype) == "Int64"
    assert r["bathrooms"] == 2.5
    assert str(out["bathrooms"].dtype) == "Float64"
    assert r["lot_acres"] == 0.14
    assert r["living_area_sqft"] == 1104
    assert r["slab"] == "Y"
    assert r["heating_cooling"] == "Both"
    assert r["roof_cover"] == "S"
    assert r["quality_class"] == "D50"
    assert r["transfer_tax_code"] == "F"


# characteristics: missing required columns is rejected
def test_sacramento_characteristics_missing_columns_raises():
    with pytest.raises(ValueError, match="missing columns"):
        C.clean(pd.DataFrame([{"PARCEL_NUMBER": "00100400120000"}]))


# Sacramento transfers / sale selection
# EVENT_DT is YYMMDD ("251220" = 2025-12-20); the lien cutoff is 2026-01-15.

def _sac_tx(*rows):
    """Transfer-list DataFrame with every EXPECTED_COLUMN (sensible defaults)."""
    base = dict(EVENT_PG="0001", MULTI_PARCEL="0", TAX_CODE="FULL",
                GRANTOR="SELLER", GRANTEE="BUYER",
                ZONING="", USE_CODE="", NBR="", SITUS="")
    return pd.DataFrame(
        [{c: str({**base, **r}.get(c, "")) for c in T.EXPECTED_COLUMNS}
         for r in rows]
    )


# transfers: a priced sale -> sale fields, YYMMDD date, title-cased names
def test_sacramento_transfers_golden_row():
    df = _sac_tx({"PARCEL_NUMBER": "001-0011-001-0000", "EVENT_DT": "251220",
                  "EVENT_PG": "0992", "STAMP_CONV": "450000", "TAX_CODE": "FULL",
                  "GRANTOR": "SMITH JOHN", "GRANTEE": "DOE JANE"})
    out = T.clean(df)
    T.validate(out)
    r = out.iloc[0]
    assert r["apn_normalized"] == "00100110010000"
    assert str(r["last_sale_date"]) == "2025-12-20"
    assert r["last_sale_price"] == 450000
    assert r["last_sale_grantor"] == "Smith John"
    assert r["is_group_sale"] == False
    assert pd.isna(r["sale_group_id"])


# transfers: a sale after the lien cutoff is dropped; the pre-cutoff one kept
def test_sacramento_transfers_lien_cutoff():
    df = _sac_tx(
        {"PARCEL_NUMBER": "P1", "EVENT_DT": "251101", "STAMP_CONV": "300000"},
        {"PARCEL_NUMBER": "P1", "EVENT_DT": "260201", "STAMP_CONV": "900000"},
        {"PARCEL_NUMBER": "P2", "EVENT_DT": "260301", "STAMP_CONV": "500000"},
    )
    out = T.clean(df).set_index("apn_normalized")
    assert out.loc["P1", "last_sale_price"] == 300000
    assert "P2" not in out.index


# transfers: the individual sale beats a later, larger group sale
def test_sacramento_transfers_prefers_individual_over_group():
    df = _sac_tx(
        {"PARCEL_NUMBER": "P1", "EVENT_DT": "250601",
         "STAMP_CONV": "400000", "MULTI_PARCEL": "0"},
        {"PARCEL_NUMBER": "P1", "EVENT_DT": "251201",
         "STAMP_CONV": "9000000", "MULTI_PARCEL": "5"},
    )
    r = T.clean(df).iloc[0]
    assert r["last_sale_price"] == 400000
    assert r["is_group_sale"] == False


# transfers: a group sale is flagged, id = EVENT_DT + EVENT_PG
def test_sacramento_transfers_group_flag_and_id():
    df = _sac_tx({"PARCEL_NUMBER": "P1", "EVENT_DT": "251220", "EVENT_PG": "0992",
                  "STAMP_CONV": "800000", "MULTI_PARCEL": "3"})
    r = T.clean(df).iloc[0]
    assert r["is_group_sale"] == True
    assert r["sale_group_id"] == "2512200992"


# transfers: unpriced tax code and the sentinel price are dropped
def test_sacramento_transfers_drops_unpriced_and_sentinel():
    df = _sac_tx(
        {"PARCEL_NUMBER": "P1", "EVENT_DT": "251201",
         "STAMP_CONV": "500000", "TAX_CODE": "NONE"},
        {"PARCEL_NUMBER": "P2", "EVENT_DT": "251201",
         "STAMP_CONV": "9", "TAX_CODE": "UNKN"},
        {"PARCEL_NUMBER": "P3", "EVENT_DT": "251201",
         "STAMP_CONV": "450000", "TAX_CODE": "PART"},
    )
    out = T.clean(df)
    assert set(out["apn_normalized"]) == {"P3"}
    assert out.iloc[0]["last_sale_price"] == 450000


# Placer secured build()
# build() reads seven pipe-delimited files; we monkeypatch _read to feed it
# synthetic frames keyed by filename, then assert on the built roll.

_AM_COLS = ["AsmtStatus", "Asmt", "FeeParcel", "Community", "StreetDirection",
            "Street", "StreetType", "StreetNum", "SpaceApt", "Zip",
            "AssesseeName", "LandUse1", "TaxabilityFull", "Acres",
            "CurrentDocDate"]
_PC_COLS = ["Asmt", "YearBuilt", "BuildingSF", "GarageSF", "Bedrooms", "Baths",
            "HalfBaths", "Pool", "Heating", "Cooling", "BuildingType", "Units",
            "ViewCode", "Fireplace"]
_TH_COLS = ["Asmt", "EventDate", "DocCode", "SalesPriceDTT", "ISGroupSale",
            "DocNum", "TransferorName", "TransfereeName"]


def _df(cols, rows):
    """DataFrame of string cells; empty-but-typed when no rows given."""
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    return pd.DataFrame([{c: str(r.get(c, "")) for c in cols} for r in rows])


def _am(*rows):
    base = dict(AsmtStatus="A", Community="AUB", StreetDirection="",
                Street="MAIN", StreetType="ST", StreetNum="100", SpaceApt="",
                Zip="95603", AssesseeName="DOE JOHN", LandUse1="01",
                TaxabilityFull="NM", Acres="", CurrentDocDate="2020-01-01")
    filled = []
    for r in rows:
        d = {**base, **r}
        d.setdefault("FeeParcel", d.get("Asmt", ""))
        filled.append(d)
    return _df(_AM_COLS, filled)


def _cv(*rows):
    base = dict(TaxYear="2026", Land="0", Structure="0", Growing="0",
                Fixtures="0", PP="0", NetValue="0", HOX="0", OtherExemption="0")
    return _df(PL._CV_COLUMNS, [{**base, **r} for r in rows])


def _th(*rows):
    base = dict(DocCode="01", ISGroupSale="0", DocNum="DOC1",
                TransferorName="SELLER", TransfereeName="BUYER")
    return _df(_TH_COLS, [{**base, **r} for r in rows])


def _pc(*rows):
    return _df(_PC_COLS, list(rows))


def _placer_build(monkeypatch, am, cv=None, th=None, pc=None, roll_year=2026):
    lu = _df(["LandUseCode", "Descr", "UseCategory"], [
        {"LandUseCode": "01", "Descr": "Single Family Residence", "UseCategory": "4"},
        {"LandUseCode": "05", "Descr": "Apartment, 4+ units", "UseCategory": "2"},
        {"LandUseCode": "00", "Descr": "Vacant Land", "UseCategory": "4"}])
    tx = _df(["TaxabilityCode", "Descr", "TransferToTxRoll"], [
        {"TaxabilityCode": "NM", "Descr": "Normal", "TransferToTxRoll": "1"},
        {"TaxabilityCode": "CA", "Descr": "Common Area", "TransferToTxRoll": "0"}])
    asr = _df(["ResourceID", "Code", "Descr"], [
        {"ResourceID": "Heating", "Code": "C", "Descr": "Central"},
        {"ResourceID": "ViewCode", "Code": "N", "Descr": "No View influence on sale"}])
    frames = {
        "AsmtMaster.csv": am,
        "LandUseCodeList.csv": lu,
        "TaxabilityCodeList.csv": tx,
        "CertifiedValues_20261.csv": cv if cv is not None else _cv(),
        "TransferHistoryTwoYear.csv": th if th is not None else _th(),
        # one blank char row per parcel so the PropChar decode maps on real keys
        "PropChar.csv": pc if pc is not None else _pc(
            *[{"Asmt": a} for a in am["Asmt"]]),
        "AsrCodeList.csv": asr,
    }
    monkeypatch.setattr(
        PL, "_read",
        lambda path, **kw: frames[str(path).split("/")[-1]].copy(),
    )
    return PL.build("/fake", roll_year)


# placer build: one parcel -> core mapped and derived fields
def test_placer_golden_row(monkeypatch):
    am = _am({"Asmt": "001010001000", "LandUse1": "01", "Acres": "0.25",
              "StreetNum": "291", "Street": "SUTTER", "StreetType": "ST"})
    cv = _cv({"Asmt": "001010001000", "Land": "200000", "Structure": "300000",
              "HOX": "7000"})
    th = _th({"Asmt": "001010001000", "EventDate": "2025-12-20",
              "SalesPriceDTT": "450000"})
    pc = _pc({"Asmt": "001010001000", "YearBuilt": "1950", "BuildingSF": "1152",
              "GarageSF": "200", "Bedrooms": "3", "Baths": "2", "HalfBaths": "1",
              "Fireplace": "1"})
    out = _placer_build(monkeypatch, am, cv, th, pc)
    PL.validate(out)
    r = out.iloc[0]
    assert r["county"] == "placer"
    assert r["apn_normalized"] == "001010001000"
    assert r["property_type"] == "single_family"
    assert r["valuation_approach"] == "cma"
    assert r["land_value"] == 200000
    assert r["total_assessed_value"] == 500000
    assert r["homeowner_exemption"] == 7000
    assert r["on_tax_roll"] == True
    assert r["living_area_sqft"] == 1152
    assert r["bedrooms"] == 3
    assert r["bathrooms"] == 2.5
    assert r["lot_acres"] == 0.25
    assert r["lot_sqft"] == 10890
    assert r["fireplace"] == "1 Fireplace"
    assert r["last_sale_price"] == 450000
    assert str(r["last_sale_date"]) == "2025-12-20"


# placer: lot_sqft = acres * 43560; blank acres is null, not zero
def test_placer_lot_sqft_from_acres(monkeypatch):
    am = _am({"Asmt": "001010001000", "Acres": "0.5"},
             {"Asmt": "001010002000", "Acres": ""})
    out = _placer_build(monkeypatch, am).set_index("apn_normalized")
    assert out.loc["001010001000", "lot_sqft"] == 21780
    assert out.loc["001010001000", "lot_acres"] == 0.5
    assert pd.isna(out.loc["001010002000", "lot_sqft"])
    assert pd.isna(out.loc["001010002000", "lot_acres"])


# placer: fireplace decoded; 0/N -> "None" (a value); junk code -> null
def test_placer_fireplace_decode(monkeypatch):
    am = _am({"Asmt": "001010001000"}, {"Asmt": "001010002000"},
             {"Asmt": "001010003000"}, {"Asmt": "001010004000"},
             {"Asmt": "001010005000"})
    pc = _pc({"Asmt": "001010001000", "Fireplace": "0"},
             {"Asmt": "001010002000", "Fireplace": "N"},
             {"Asmt": "001010003000", "Fireplace": "1"},
             {"Asmt": "001010004000", "Fireplace": "W"},
             {"Asmt": "001010005000", "Fireplace": "Z"})
    out = _placer_build(monkeypatch, am, pc=pc).set_index("apn_normalized")
    assert out.loc["001010001000", "fireplace"] == "None"
    assert out.loc["001010002000", "fireplace"] == "None"
    assert out.loc["001010003000", "fireplace"] == "1 Fireplace"
    assert out.loc["001010004000", "fireplace"] == "Wood Stove"
    assert pd.isna(out.loc["001010005000", "fireplace"])


# placer: the individual sale beats a later, larger group sale
def test_placer_prefers_individual_over_group_sale(monkeypatch):
    am = _am({"Asmt": "001010001000"})
    th = _th(
        {"Asmt": "001010001000", "EventDate": "2025-06-01",
         "SalesPriceDTT": "400000", "ISGroupSale": "0", "DocNum": "IND"},
        {"Asmt": "001010001000", "EventDate": "2025-12-01",
         "SalesPriceDTT": "9000000", "ISGroupSale": "1", "DocNum": "GRP"},
    )
    r = _placer_build(monkeypatch, am, th=th).iloc[0]
    assert r["last_sale_price"] == 400000
    assert r["is_group_sale"] == False
    assert pd.isna(r["sale_group_id"])


# placer: a group sale is flagged, id = DocNum
def test_placer_group_sale_flagged_with_docnum(monkeypatch):
    am = _am({"Asmt": "001010001000"})
    th = _th({"Asmt": "001010001000", "EventDate": "2025-12-01",
              "SalesPriceDTT": "800000", "ISGroupSale": "1", "DocNum": "2025R1"})
    r = _placer_build(monkeypatch, am, th=th).iloc[0]
    assert r["is_group_sale"] == True
    assert r["sale_group_id"] == "2025R1"
    assert r["last_sale_price"] == 800000


# placer: a sale after the lien cutoff is dropped; the pre-cutoff one kept
def test_placer_sale_lien_cutoff(monkeypatch):
    am = _am({"Asmt": "001010001000"}, {"Asmt": "001010002000"})
    th = _th(
        {"Asmt": "001010001000", "EventDate": "2025-11-01", "SalesPriceDTT": "300000"},
        {"Asmt": "001010001000", "EventDate": "2026-02-01", "SalesPriceDTT": "900000"},
        {"Asmt": "001010002000", "EventDate": "2026-03-01", "SalesPriceDTT": "500000"},
    )
    out = _placer_build(monkeypatch, am, th=th).set_index("apn_normalized")
    assert out.loc["001010001000", "last_sale_price"] == 300000
    assert pd.isna(out.loc["001010002000", "last_sale_price"])


# placer: distinct parcels each get their own values (the join is 1:1)
def test_placer_certified_values_no_fanout(monkeypatch):
    am = _am({"Asmt": "001010001000"}, {"Asmt": "001010002000"})
    cv = _cv({"Asmt": "001010001000", "Land": "100000", "Structure": "200000"},
             {"Asmt": "001010002000", "Land": "230000", "Structure": "459630"})
    out = _placer_build(monkeypatch, am, cv=cv).set_index("apn_normalized")
    assert out.loc["001010001000", "total_assessed_value"] == 300000
    assert out.loc["001010002000", "total_assessed_value"] == 689630


# placer: a repeated exemption amount is copied to each parcel (not mangled)
def test_placer_shared_exemption_copied_to_each(monkeypatch):
    am = _am({"Asmt": "001010001000"}, {"Asmt": "001010002000"})
    cv = _cv({"Asmt": "001010001000", "Land": "500000", "OtherExemption": "180671"},
             {"Asmt": "001010002000", "Land": "600000", "OtherExemption": "180671"})
    out = _placer_build(monkeypatch, am, cv=cv).set_index("apn_normalized")
    assert out.loc["001010001000", "other_exemption"] == 180671
    assert out.loc["001010002000", "other_exemption"] == 180671


# placer: multi-row PropChar keeps the largest structure, never sums them
def test_placer_propchar_keeps_largest_structure_not_summed(monkeypatch):
    am = _am({"Asmt": "001010001000"})
    pc = _pc({"Asmt": "001010001000", "BuildingSF": "800", "Bedrooms": "1"},
             {"Asmt": "001010001000", "BuildingSF": "2000", "Bedrooms": "4"})
    r = _placer_build(monkeypatch, am, pc=pc).iloc[0]
    assert r["living_area_sqft"] == 2000
    assert r["bedrooms"] == 4


# placer validate: a sale dated on/after the lien cutoff is rejected
def test_placer_validate_flags_post_cutoff_sale(monkeypatch):
    out = _placer_build(monkeypatch, _am({"Asmt": "001010001000"}))
    out["last_sale_price"] = 500000
    out["last_sale_date"] = pd.Timestamp("2026-03-01")
    with pytest.raises(ValueError, match="cutoff"):
        PL.validate(out)


# placer validate: a sale_group_id on a non-group sale is rejected
def test_placer_validate_flags_orphan_group_id(monkeypatch):
    out = _placer_build(monkeypatch, _am({"Asmt": "001010001000"}))
    out.loc[0, "sale_group_id"] = "X"
    with pytest.raises(ValueError, match="sale_group_id"):
        PL.validate(out)


# transfers validate: a sale dated on/after the lien cutoff is rejected
def test_sacramento_transfers_validate_flags_post_cutoff():
    out = T.clean(_sac_tx({"PARCEL_NUMBER": "P1", "EVENT_DT": "251201",
                           "STAMP_CONV": "400000"}))
    out["last_sale_date"] = pd.Timestamp("2026-03-01")
    with pytest.raises(ValueError, match="cutoff"):
        T.validate(out)
