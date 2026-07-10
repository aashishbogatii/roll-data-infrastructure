"""Vectorized parser edge cases — the details that already bit us (float money,
dropped leading zeros)."""

import pandas as pd

from roll_pipeline.parsers import col_int, col_numstr, col_str, col_title


def test_col_int_is_int64_not_float():
    out = col_int(pd.Series(["490338", "612928"]))
    assert str(out.dtype) == "Int64"          # money never float
    assert out.iloc[0] == 490338


def test_col_int_handles_blanks_commas_floats_garbage():
    out = col_int(pd.Series(["", "1,234", "462.0", "abc", "0"]))
    assert pd.isna(out.iloc[0])               # blank -> NA
    assert out.iloc[1] == 1234                # comma stripped
    assert out.iloc[2] == 462                 # '.0' float
    assert pd.isna(out.iloc[3])               # garbage -> NA
    assert out.iloc[4] == 0                   # zero kept


def test_col_str_preserves_leading_zeros():
    out = col_str(pd.Series(["03169", "  x  ", ""]))
    assert out.iloc[0] == "03169"             # TRA/zip leading zero kept
    assert out.iloc[1] == "x"                 # stripped
    assert pd.isna(out.iloc[2])               # empty -> NA


def test_col_numstr_strips_trailing_dot_zero():
    out = col_numstr(pd.Series(["20.0", "95811.0", "03169", ""]))
    assert out.iloc[0] == "20"                # numeric code, .0 dropped
    assert out.iloc[1] == "95811"
    assert out.iloc[2] == "03169"             # no .0 -> unchanged, zero kept
    assert pd.isna(out.iloc[3])


def test_col_title():
    out = col_title(pd.Series(["JIBBOOM ST", "cross roads inn", ""]))
    assert out.iloc[0] == "Jibboom St"
    assert out.iloc[1] == "Cross Roads Inn"
    assert pd.isna(out.iloc[2])
