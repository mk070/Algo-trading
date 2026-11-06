"""Tests for Immutable Research Snapshot and Deterministic Canonical Verification."""

import datetime
import json
from pathlib import Path
import pandas as pd
import pytest

from app.engine.research_snapshot import (
    CANONICAL_COLUMNS,
    format_canonical_cell,
    serialize_record_tuple,
    compute_canonical_data_sha256,
    compute_file_sha256,
    verify_research_snapshot,
)


def _make_sample_record(symbol="AAPL", date=datetime.date(2023, 1, 3), close=150.25, volume=1000000.0):
    return (
        symbol,
        date,
        149.00,  # open
        151.00,  # high
        148.50,  # low
        close,   # close
        close,   # adj_close
        volume,  # volume
        "alpaca_iex",  # source
        149.00,  # split_adj_open
        151.00,  # split_adj_high
        148.50,  # split_adj_low
        close,   # split_adj_close
        1.0,     # dividend_factor
        True,    # is_split_adjusted
        datetime.datetime(2023, 1, 3, 20, 0, 0, tzinfo=datetime.timezone.utc),  # ingested_at
    )


def test_deterministic_cell_formatting():
    # Price formatting
    assert format_canonical_cell("open", 150.25) == "150.250000"
    assert format_canonical_cell("open", None) == "NULL"
    assert format_canonical_cell("split_adj_open", None) == "NULL"

    # Volume formatting
    assert format_canonical_cell("volume", 543210.5) == "543210.5000"
    assert format_canonical_cell("volume", 100) == "100.0000"

    # Source formatting
    assert format_canonical_cell("source", " Alpaca_IEX ") == "alpaca_iex"

    # Date formatting
    assert format_canonical_cell("date", datetime.date(2023, 5, 10)) == "2023-05-10"

    # Ingested_at formatting
    ts = datetime.datetime(2023, 5, 10, 14, 30, 45, tzinfo=datetime.timezone.utc)
    assert format_canonical_cell("ingested_at", ts) == "2023-05-10T14:30:45Z"


def test_stable_canonical_sha256_for_identical_logical_records():
    records_1 = [
        _make_sample_record("AAPL", datetime.date(2023, 1, 3), 150.25),
        _make_sample_record("MSFT", datetime.date(2023, 1, 3), 240.50),
    ]
    records_2 = [
        _make_sample_record("AAPL", datetime.date(2023, 1, 3), 150.25),
        _make_sample_record("MSFT", datetime.date(2023, 1, 3), 240.50),
    ]

    h1 = compute_canonical_data_sha256(records_1)
    h2 = compute_canonical_data_sha256(records_2)
    assert h1 == h2
    assert len(h1) == 64


def test_different_sha256_when_record_changes():
    base_records = [
        _make_sample_record("AAPL", datetime.date(2023, 1, 3), 150.25),
    ]
    modified_records = [
        _make_sample_record("AAPL", datetime.date(2023, 1, 3), 150.26),  # 1 cent change
    ]

    h_base = compute_canonical_data_sha256(base_records)
    h_mod = compute_canonical_data_sha256(modified_records)
    assert h_base != h_mod


def test_row_order_independence_after_canonical_sorting():
    rec_a = _make_sample_record("AAPL", datetime.date(2023, 1, 3), 150.25)
    rec_b = _make_sample_record("MSFT", datetime.date(2023, 1, 3), 240.50)

    # Inverted list
    unsorted_records = [rec_b, rec_a]
    sorted_records = sorted(unsorted_records, key=lambda r: (r[0], r[1]))

    canonical_records = [rec_a, rec_b]
    assert compute_canonical_data_sha256(sorted_records) == compute_canonical_data_sha256(canonical_records)


def test_null_and_numeric_precision_handling():
    rec_with_nulls = (
        "SPY",
        datetime.date(2023, 1, 3),
        380.0,
        385.0,
        379.0,
        382.5,
        382.5,
        50000000.0,
        "yfinance",
        None,  # split_adj_open is NULL
        None,  # split_adj_high is NULL
        None,  # split_adj_low is NULL
        None,  # split_adj_close is NULL
        1.0,
        False,
        datetime.datetime(2023, 1, 3, 20, 0, 0, tzinfo=datetime.timezone.utc),
    )
    serialized = serialize_record_tuple(rec_with_nulls)
    assert "NULL\tNULL\tNULL\tNULL" in serialized
    assert "false" in serialized
    assert serialized.endswith("\n")


def test_manifest_consistency():
    manifest_path = Path("data/research/research_snapshot_manifest.json")
    parquet_path = Path("data/research/research_snapshot_20261106.parquet")

    assert manifest_path.exists(), "Manifest file must exist"
    assert parquet_path.exists(), "Parquet snapshot file must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["snapshot_id"] == "research_snapshot_20261106_neon_daily"
    assert manifest["row_count"] == 141040
    assert manifest["symbol_count"] == 114
    assert manifest["date_min"] == "2021-07-19"
    assert manifest["date_max"] == "2026-11-05"
    assert manifest["columns"] == CANONICAL_COLUMNS
    assert len(manifest["parquet_file_sha256"]) == 64
    assert len(manifest["canonical_data_sha256"]) == 64


def test_parquet_file_integrity_and_restoration():
    result = verify_research_snapshot(
        parquet_path="data/research/research_snapshot_20261106.parquet",
        manifest_path="data/research/research_snapshot_manifest.json",
    )
    assert result["status"] == "VERIFIED"
    assert result["row_count"] == 141040
    assert result["symbol_count"] == 114


def test_restoration_verification_fails_when_tampered(tmp_path):
    # Create a small valid parquet and manifest
    records = [
        _make_sample_record("AAPL", datetime.date(2023, 1, 3), 150.25),
        _make_sample_record("MSFT", datetime.date(2023, 1, 3), 240.50),
    ]
    df = pd.DataFrame(records, columns=CANONICAL_COLUMNS)
    p_path = tmp_path / "test.parquet"
    m_path = tmp_path / "manifest.json"

    df.to_parquet(p_path, engine="pyarrow", index=False)
    file_sha = compute_file_sha256(p_path)
    data_sha = compute_canonical_data_sha256(records)

    manifest = {
        "parquet_file_sha256": file_sha,
        "canonical_data_sha256": data_sha,
        "columns": CANONICAL_COLUMNS,
        "row_count": len(df),
        "symbol_count": 2,
    }
    with open(m_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    # 1. Verification passes on clean file
    res = verify_research_snapshot(parquet_path=p_path, manifest_path=m_path)
    assert res["status"] == "VERIFIED"

    # 2. Tamper the parquet file by altering a row
    df_tampered = df.copy()
    df_tampered.loc[0, "close"] = 999.99
    p_tampered = tmp_path / "tampered.parquet"
    df_tampered.to_parquet(p_tampered, engine="pyarrow", index=False)

    # Verification must fail with mismatch error
    with pytest.raises(ValueError, match="Parquet file SHA-256 mismatch"):
        verify_research_snapshot(parquet_path=p_tampered, manifest_path=m_path)

