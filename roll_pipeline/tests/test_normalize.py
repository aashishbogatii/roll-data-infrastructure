"""Key-derivation tests — the join contract. If these break, lookups silently
return wrong or empty data."""

from roll_pipeline.normalize import join_apn, normalize_situs, strip_apn


def test_join_apn_pads_and_dashes():
    # unpadded and padded inputs both canonicalize the same way
    assert join_apn(("1", 3), ("11", 4), ("1", 3), ("0", 4)) == "001-0011-001-0000"
    assert join_apn(("001", 3), ("0011", 4), ("001", 3), ("0000", 4)) == "001-0011-001-0000"


def test_join_apn_five_part_unsecured():
    assert (
        join_apn(("001", 3), ("0011", 4), ("001", 3), ("0000", 4), ("0002", 4))
        == "001-0011-001-0000-0002"
    )


def test_join_apn_none_if_any_component_missing():
    assert join_apn(("001", 3), (None, 4), ("001", 3), ("0000", 4)) is None
    assert join_apn(("001", 3), ("", 4), ("001", 3), ("0000", 4)) is None


def test_strip_apn():
    assert strip_apn("001-0011-001-0000") == "00100110010000"          # 14-digit key
    assert strip_apn("00100110010000") == "00100110010000"             # already stripped
    assert strip_apn("001-0011-001-0000-0002") == "001001100100000002"  # 18-digit
    assert strip_apn(None) is None
    assert strip_apn("") is None


def test_secured_and_unsecured_keys_are_length_distinct():
    # Why a caller-blind lookup can auto-resolve the roll.
    assert len(strip_apn("001-0011-001-0000")) == 14
    assert len(strip_apn("001-0011-001-0000-0002")) == 18


def test_normalize_situs_comma_format_with_state():
    a = normalize_situs(432, "42ND ST", 95819, city="SACRAMENTO", state="CA")
    assert a == "432 42ND ST, SACRAMENTO, CA 95819"
    assert a.split(", ") == ["432 42ND ST", "SACRAMENTO", "CA 95819"]


def test_normalize_situs_matches_across_suffix_and_case():
    # 'Street' vs 'ST' and mixed case must collapse to the same key.
    a = normalize_situs("432", "42nd Street", "95819", city="Sacramento", state="CA")
    b = normalize_situs(432, "42ND ST", 95819, city="SACRAMENTO", state="CA")
    assert a == b


def test_normalize_situs_zip5_from_float_string():
    # unsecured zips read as '95811.0' -> keep 5 digits
    a = normalize_situs("221", "JIBBOOM ST", "95811.0", city="SACRAMENTO", state="CA")
    assert a.endswith("95811")


def test_normalize_situs_none_without_street():
    assert normalize_situs(None, None, 95811, city="SACRAMENTO") is None
