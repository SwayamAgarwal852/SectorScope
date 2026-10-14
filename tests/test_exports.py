"""Checks on the Power BI CSV exports."""

import duckdb
import pytest

import export_powerbi
from conftest import N_PERIODS, N_RETURN_DAYS, N_SECTORS, N_TICKERS, ROLLING_WINDOW

EXPECTED = {
    "ticker_daily.csv": (
        N_TICKERS * N_RETURN_DAYS,
        ["trade_date", "ticker", "sector", "close", "volume", "daily_return", "log_return", "cumulative_return"],
    ),
    "sector_daily.csv": (
        N_SECTORS * N_RETURN_DAYS,
        ["trade_date", "sector", "n_constituents", "daily_return", "cumulative_return"],
    ),
    "sector_summary.csv": (
        N_SECTORS * N_PERIODS,
        ["sector", "n_constituents", "tickers", "period_type", "period", "period_start", "period_end",
         "n_return_days", "total_return", "annualized_return", "annualized_volatility", "return_to_risk",
         "max_drawdown"],
    ),
    "ticker_risk_return.csv": (
        N_TICKERS * N_PERIODS,
        ["ticker", "sector", "period_type", "period", "period_start", "period_end", "n_return_days",
         "total_return", "annualized_return", "annualized_volatility", "return_to_risk", "max_drawdown"],
    ),
    "correlation.csv": (
        N_TICKERS**2,
        ["ticker_a", "sector_a", "ticker_b", "sector_b", "correlation", "n_obs"],
    ),
    "sector_correlation.csv": (
        N_SECTORS**2,
        ["sector_a", "sector_b", "correlation", "n_obs"],
    ),
    "ticker_rolling_volatility.csv": (
        N_TICKERS * (N_RETURN_DAYS - ROLLING_WINDOW + 1),
        ["trade_date", "ticker", "sector", "rolling_vol_30d", "rolling_vol_30d_annualized"],
    ),
    "sector_rolling_volatility.csv": (
        N_SECTORS * (N_RETURN_DAYS - ROLLING_WINDOW + 1),
        ["trade_date", "sector", "rolling_vol_30d", "rolling_vol_30d_annualized"],
    ),
}


def test_exactly_eight_exports_defined():
    assert set(export_powerbi.EXPORTS) == set(EXPECTED)


def test_export_directory_contains_all_files(export_dir):
    assert {p.name for p in export_dir.glob("*.csv")} == set(EXPECTED)


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_export_shape(export_dir, filename):
    rel = duckdb.read_csv(str(export_dir / filename))
    expected_rows, expected_columns = EXPECTED[filename]
    assert rel.columns == expected_columns
    assert rel.shape[0] == expected_rows


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_export_has_no_nulls_or_blanks(export_dir, filename):
    # Read every column as text so empty strings are caught as well as NULLs.
    path = str(export_dir / filename)
    rel = duckdb.read_csv(path, all_varchar=True)
    per_column = duckdb.sql(
        "SELECT SUM(CASE WHEN COLUMNS(*) IS NULL OR trim(COLUMNS(*)) = '' THEN 1 ELSE 0 END) FROM rel"
    ).fetchone()
    blanks = {col: n for col, n in zip(rel.columns, per_column) if n}
    assert blanks == {}


def test_ticker_daily_starts_on_first_return_date(export_dir):
    rel = duckdb.read_csv(str(export_dir / "ticker_daily.csv"))
    assert str(duckdb.sql("SELECT MIN(trade_date) FROM rel").fetchone()[0]) == "2020-01-03"


def test_export_refuses_tables_with_nulls(tmp_path, monkeypatch):
    monkeypatch.setattr(
        export_powerbi, "EXPORTS", {"bad.csv": "SELECT ticker, daily_return FROM ticker_daily_returns"}
    )
    with pytest.raises(ValueError, match="contain nulls"):
        export_powerbi.export(export_dir=tmp_path, db_path=tmp_path / "bad.duckdb")
    assert not (tmp_path / "bad.csv").exists()
