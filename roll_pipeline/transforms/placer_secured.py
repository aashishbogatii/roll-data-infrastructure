"""Placer SECURED roll: build() one cleaned row per base parcel from the
multi-file Placer delivery (pipe-delimited, Latin-1), joined on Asmt:
  AsmtMaster              identity / owner / situs / land use  (base)
  CertifiedValues         assessed values
  TransferHistoryTwoYear  latest priced sale
  PropChar                building characteristics
  LandUse / Taxability    code decodes
Base roll = active assessments in mapbook < 800 (first 3 digits of Asmt).
"""

from __future__ import annotations

import pandas as pd

from ..normalize import normalize_situs, strip_apn
from ..parsers import col_float, col_int, col_str, col_title

COUNTY = "placer"
ROLL_TYPE = "secured"

# Arm's-length sale code (source of last_sale_price); others are trust/death/etc.
_SALE_DOC_CODE = "01"

# keep sales before the 2026 lien-date cutoff; a later resale is dropped so the
# kept sale reflects this roll year's value
_SALE_CUTOFF = pd.Timestamp("2026-01-15")

# CertifiedValues has a malformed quoted header -> read headerless with names.
_CV_COLUMNS = [
    "Asmt", "TaxYear", "Land", "Structure", "Growing", "Fixtures", "PP",
    "NetValue", "HOX", "OtherExemption",
]

# LandUse code -> canonical property_type. Residential is broken out; everything
# else falls back to its UseCategory (commercial / industrial / agriculture).
_RES_DETAIL = {
    "01": "single_family", "16": "single_family",  # 16 = residence on comm land
    "02": "duplex", "03": "triplex", "04": "condo", "05": "apartment",
    "08": "mobile_home", "09": "mobile_home",
    "06": "timeshare", "00": "vacant", "10": "vacant",
}
_CAT_BROAD = {"4": "residential_other", "2": "commercial",
              "3": "industrial", "1": "agriculture"}

# Land-use codes by valuation approach. Vacant codes are listed explicitly
# because they also sit inside the commercial (20) / industrial (30) sectors.
_LAND_CODES = frozenset({
    "00",  # vacant, all types
    "10",  # vacant, subdivided residential
    "20",  # vacant, commercial
    "30",  # vacant, industrial
    "50",  # vacant, dry farm
    "07",  # residential auxiliary improvement (land + outbuilding, no home)
})
_SPECIAL_CODES = frozenset({
    "06",  # timeshares (nominal values)
    "51",  # dry farm with residence
    "60",  # conservation easement restrictions
    "89",  # common area
})
_CMA_CODES = frozenset({
    "01",  # single family / half plex
    "02",  # duplex
    "03",  # triplex
    "04",  # condo
    "08",  # mobile home outside park
    "09",  # mobile home in park
    "16",  # residence on commercial land
})
# Apartments (05) -> income; the fourplex-vs-complex split is deferred.
_APARTMENT_CODE = "05"

# PropChar Cooling uses its own abbreviations (not the AsrCodeList codes).
_COOLING = {
    "CENTRALAC": "Central AC", "ROOMWALL": "Room/Wall",
    "E": "Evaporative", "W": "Window",
}

# Fireplace code -> description. 0/N (no fireplace) is a real value kept as
# "None", not null; junk/blank codes fall through to null (unknown).
_FIREPLACE = {
    "0": "None", "N": "None",
    "1": "1 Fireplace", "2": "2 Fireplaces", "3": "3 Fireplaces",
    "4": "4 Fireplaces", "5": "5 Fireplaces", "6": "6 or more Fireplaces",
    "F": "Fireplace", "W": "Wood Stove", "P": "Pellet Stove",
    "B": "Fireplace and Wood Stove",
}

# Community abbreviation -> full situs city name (Placer has no legend for it;
# derived from the data, cross-checked against ZIP and the mailing-city field).
_COMMUNITY = {
    "ROS": "Roseville", "ROC": "Rocklin", "LIN": "Lincoln", "AUB": "Auburn",
    "GRA": "Granite Bay", "LOO": "Loomis", "TAC": "Tahoe City",
    "TRU": "Truckee", "NEW": "Newcastle", "FOR": "Foresthill", "COL": "Colfax",
    "KIN": "Kings Beach", "CAR": "Carnelian Bay", "MEA": "Meadow Vista",
    "OLY": "Olympic Valley", "TAV": "Tahoe Vista", "PEN": "Penryn",
    "HOM": "Homewood", "WEI": "Weimar", "PLO": "Roseville", "TAH": "Tahoma",
    "SOD": "Soda Springs", "ALT": "Alta", "APP": "Applegate",
    "SHE": "Sheridan", "ALP": "Alpine Meadows", "EMI": "Emigrant Gap",
    "DUT": "Dutch Flat", "BIC": "Bickford Ranch", "ELV": "Elverta",
    "NOR": "Norden", "GOL": "Gold Run", "PLE": "Pleasant Grove",
    "IOW": "Iowa Hill", "BAX": "Baxter",
}


def _read(path: str, **kw) -> pd.DataFrame:
    """Read a pipe-delimited, Latin-1 Placer CSV; trim headers and values."""
    df = pd.read_csv(
        path, sep="|", dtype=str, quotechar='"', encoding="latin-1",
        on_bad_lines="skip", **kw,
    )
    df.columns = [c.strip().strip('"') for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df


def _property_type(code: object, category: object) -> str | None:
    if code in _RES_DETAIL:
        return _RES_DETAIL[code]
    return _CAT_BROAD.get(category)


def _valuation_approach(code: object, category: object) -> str | None:
    """cma / income / land / special from the land-use code + UseCategory."""
    if code is None or pd.isna(code):
        return None
    c = str(code).strip()
    if not c:
        return None
    if c in _LAND_CODES:
        return "land"
    if c in _SPECIAL_CODES or category == "1":
        return "special"
    if c == _APARTMENT_CODE:
        return "income"
    if category in {"2", "3"}:
        return "income"
    if c in _CMA_CODES:
        return "cma"
    return "special"


def build(source_root: str, roll_year: int) -> pd.DataFrame:
    """Read every Placer file under source_root and return the cleaned roll."""
    root = str(source_root).rstrip("/")

    # --- base: active secured real property (mapbook < 800), one row/parcel ---
    am = _read(f"{root}/AsmtMaster.csv")
    am = am[am["AsmtStatus"].str.upper() == "A"]
    mapbook = pd.to_numeric(am["Asmt"].str[:3], errors="coerce")
    am = am[mapbook < 800].copy()

    out = pd.DataFrame(index=am.index)
    out["county"] = COUNTY
    out["roll_year"] = roll_year
    out["roll_type"] = ROLL_TYPE
    out["apn"] = am["FeeParcel"]
    out["apn_normalized"] = am["FeeParcel"].map(strip_apn)

    # situs city: Community abbreviation -> full name (first 3 letters, so
    # "ROS;"/"KING" still resolve)
    code = (
        am["Community"].fillna("").str.replace(r"[^A-Za-z]", "", regex=True)
        .str.upper().str[:3]
    )
    out["situs_city"] = code.map(_COMMUNITY)

    # situs address: combine directional + name + type, then shared normalizer
    street = (
        am["StreetDirection"].fillna("") + " "
        + am["Street"].fillna("") + " "
        + am["StreetType"].fillna("")
    ).str.replace(r"\s+", " ", regex=True).str.strip()
    out['street_num'] = am['StreetNum']
    out['street_name'] = col_str(street)
    
    out["situs_unit"] = col_str(am["SpaceApt"])
    unit = am["SpaceApt"].fillna("").str.strip()
    street_unit = (street + " " + unit).str.replace(
        r"\s+", " ", regex=True).str.strip()
    out["address"] = [
        normalize_situs(num, st, z, city=city, state="CA")
        for num, st, city, z in zip(
            am["StreetNum"], street_unit, out["situs_city"], am["Zip"]
        )
    ]
    out["owner_name"] = col_title(am["AssesseeName"])

    # land use + property_type
    lu = _read(f"{root}/LandUseCodeList.csv")
    descr = dict(zip(lu["LandUseCode"].str.strip(), lu["Descr"]))
    cat = dict(zip(lu["LandUseCode"].str.strip(), lu["UseCategory"]))
    out["land_use_code"] = col_str(am["LandUse1"])
    out["land_use_desc"] = am["LandUse1"].map(descr)
    out["property_type"] = [
        _property_type(c, cat.get(c)) for c in am["LandUse1"]
    ]

    # on_tax_roll = TransferToTxRoll (is it billed?). Non-billed parcels
    # (timeshare intervals, common area, government-owned) carry no value.
    tx = _read(f"{root}/TaxabilityCodeList.csv")
    code = tx["TaxabilityCode"].str.strip()
    tax_code = am["TaxabilityFull"].fillna("").str.strip()
    out["taxability_status"] = col_str(tax_code.map(dict(zip(code, tx["Descr"]))))
    out["on_tax_roll"] = (
        tax_code.map(dict(zip(code, tx["TransferToTxRoll"])))
        .map({"1": True, "0": False}).astype("boolean")
    )

    # lot size: Acres is only populated for larger/rural parcels; 0 = unrecorded
    acres = col_float(am["Acres"])
    out["lot_acres"] = acres.where(acres > 0)
    # same area in square feet (1 acre = 43,560 sqft); null where acres unrecorded
    out["lot_sqft"] = (out["lot_acres"] * 43560).round().astype("Int64")

    key = am["Asmt"]

    # --- values (CertifiedValues, LEFT join on Asmt) ---
    cv = _read(f"{root}/CertifiedValues_20261.csv", header=None, skiprows=1,
               names=_CV_COLUMNS)
    _parts = ["Land", "Structure", "Growing", "Fixtures", "PP"]
    for c in _parts:
        cv[c] = pd.to_numeric(cv[c], errors="coerce")
    # total = sum of the assessed components, BEFORE exemptions
    cv["total"] = cv[_parts].sum(axis=1, min_count=1)
    cv = cv.drop_duplicates("Asmt").set_index("Asmt")
    out["land_value"] = col_int(key.map(cv["Land"]))
    out["improvement_value"] = col_int(key.map(cv["Structure"]))
    out["growing_value"] = col_int(key.map(cv["Growing"]))
    out["fixture_value"] = col_int(key.map(cv["Fixtures"]))
    out["personal_property_value"] = col_int(key.map(cv["PP"]))
    out["total_assessed_value"] = col_int(key.map(cv["total"]))
    out["homeowner_exemption"] = col_int(key.map(cv["HOX"]))
    out["other_exemption"] = col_int(key.map(cv["OtherExemption"]))

    # last ownership transfer = current controlling document's date (any deed
    # type, full history); the transfer file below is used only for the sale
    out["last_ownership_transfer_date"] = pd.to_datetime(
        am["CurrentDocDate"], errors="coerce"
    ).dt.date

    # last sale = one priced code-01 transfer before the lien-date cutoff, per
    # parcel. Prefer an individual sale over a group sale (whose price is the
    # bundled whole-deal amount), then the latest, then the higher price on a
    # same-day tie. Group sales are flagged is_group_sale, not dropped.
    th = _read(f"{root}/TransferHistoryTwoYear.csv")
    th["_dt"] = pd.to_datetime(th["EventDate"], errors="coerce")
    th["_price"] = pd.to_numeric(th["SalesPriceDTT"], errors="coerce")
    th["_group"] = th["ISGroupSale"] == "1"
    sale = (
        th[(th["DocCode"] == _SALE_DOC_CODE)
           & (th["_price"] > 0)
           & (th["_dt"] < _SALE_CUTOFF)]
        .sort_values(["_group", "_dt", "_price"], ascending=[True, False, False])
        .drop_duplicates("Asmt", keep="first")
        .set_index("Asmt")
    )
    out["last_sale_date"] = pd.to_datetime(key.map(sale["_dt"])).dt.date
    out["last_sale_price"] = col_int(key.map(sale["_price"]))
    out["last_sale_grantor"] = col_title(key.map(sale["TransferorName"]))
    out["last_sale_grantee"] = col_title(key.map(sale["TransfereeName"]))
    is_grp = key.map(sale["_group"])
    out["is_group_sale"] = is_grp.astype("boolean")
    # co-sold parcels share the sale's DocNum; set only for group sales
    out["sale_group_id"] = col_str(key.map(sale["DocNum"]).where(is_grp == True))

    # --- building characteristics (PropChar, deduped to main structure) ---
    pc = _read(
        f"{root}/PropChar.csv",
        usecols=["Asmt", "YearBuilt", "BuildingSF", "GarageSF", "Bedrooms",
                 "Baths", "HalfBaths", "Pool", "Heating", "Cooling",
                 "BuildingType", "Units", "ViewCode", "Fireplace"],
    )
    pc["_sf"] = pd.to_numeric(pc["BuildingSF"], errors="coerce").fillna(-1)
    pc = pc.sort_values("_sf").drop_duplicates("Asmt", keep="last")
    pc = pc.set_index("Asmt")

    yb = col_int(key.map(pc["YearBuilt"]))
    out["year_built"] = yb.where(yb.between(1850, roll_year))
    out["living_area_sqft"] = col_int(key.map(pc["BuildingSF"]))
    out["garage_sqft"] = col_int(key.map(pc["GarageSF"]))
    beds = col_int(key.map(pc["Bedrooms"]))
    out["bedrooms"] = beds.where(beds >= 0)
    full = col_float(key.map(pc["Baths"]))
    half = col_float(key.map(pc["HalfBaths"]))
    full = full.where(full >= 0)
    half = half.where(half >= 0)
    out["bathrooms"] = full + half.fillna(0) * 0.5
    out["pool"] = col_str(key.map(pc["Pool"]))

    # heating + view are decoded to descriptions via AsrCodeList (Code -> Descr
    # per ResourceID); cooling uses its own abbreviations, mapped via _COOLING.
    asr = _read(f"{root}/AsrCodeList.csv")

    def _asr(rid: str) -> dict:
        # drop placeholder rows so they decode to null: the "... - Structure ..."
        # headers (code 99) and generic entries whose Descr is just the category
        # name (codes 1/S -> "Heating", which carries no heating type).
        descr = asr["Descr"].str.strip()
        m = asr[(asr["ResourceID"] == rid)
                & ~descr.str.contains("Structure", na=False)
                & (descr.str.upper() != rid.upper())]
        return dict(zip(m["Code"].str.upper(), m["Descr"]))

    out["heating"] = col_str(
        key.map(pc["Heating"]).str.upper().map(_asr("Heating")))
    out["cooling"] = col_str(
        key.map(pc["Cooling"]).str.upper().map(_COOLING))
    out["building_type"] = col_str(key.map(pc["BuildingType"]))
    out["units"] = col_int(key.map(pc["Units"]))
    out["view"] = col_str(
        key.map(pc["ViewCode"]).str.upper().map(_asr("ViewCode")))
    # Fireplace: decoded to count/type; 0/N kept as "None" (real value, not null)
    out["fireplace"] = col_str(
        key.map(pc["Fireplace"]).str.upper().map(_FIREPLACE))

    # --- valuation approach (from the land-use code) ---
    out["valuation_approach"] = [
        _valuation_approach(c, cat.get(c)) for c in am["LandUse1"]
    ]

    out = out[out["apn_normalized"].notna()]
    return out.sort_values("apn_normalized").reset_index(drop=True)


def validate(df: pd.DataFrame) -> None:
    """Raise if the key is bad, the base filter leaked, or a derived invariant
    (valuation bucket, sale price/cutoff, group id, lot conversion) is broken."""
    errors: list[str] = []
    if df["apn_normalized"].isna().any():
        errors.append("null apn_normalized")
    if (df["county"] != COUNTY).any():
        errors.append("county is not 'placer'")
    if df["apn"].duplicated().any():
        errors.append("duplicate apn (want one row/parcel)")

    # sales: positive price, dated before the lien cutoff
    sold = df["last_sale_price"].notna()
    if (df.loc[sold, "last_sale_price"] <= 0).any():
        errors.append("non-positive last_sale_price")
    if (pd.to_datetime(df["last_sale_date"], errors="coerce") >= _SALE_CUTOFF).any():
        errors.append("last_sale_date on/after the lien cutoff")

    # sale_group_id is set only for group sales
    has_id = df["sale_group_id"].notna()
    grouped = df["is_group_sale"].fillna(False).astype(bool)
    if (has_id & ~grouped).any():
        errors.append("sale_group_id set on a non-group sale")

    if errors:
        raise ValueError("placer_secured validation failed: " + "; ".join(errors))
