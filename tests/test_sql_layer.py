"""Shape and correctness checks for the DuckDB views built from sql/."""

import math

import pytest

import validate_data
from export_powerbi import null_counts
from conftest import (
    EXPECTED_SECTORS,
    N_DATES,
    N_PERIODS,
    N_RETURN_DAYS,
    N_SECTORS,
    N_TICKERS,
    ROLLING_WINDOW,
    scalar,
)


def test_raw_file_passes_validation():
    assert validate_data.main() == 0


# ---------------------------------------------------------------- shapes

@pytest.mark.parametrize(
    "view, expected",
    [
        ("raw_prices", N_TICKERS * N_DATES),
        ("prices", N_TICKERS * N_DATES),
        ("ticker_daily_returns", N_TICKERS * N_DATES),
        ("ticker_rolling_volatility", N_TICKERS * (N_RETURN_DAYS - ROLLING_WINDOW + 1)),
        ("sector_daily_returns", N_SECTORS * N_RETURN_DAYS),
        ("sector_cumulative_returns", N_SECTORS * N_RETURN_DAYS),
        ("sector_rolling_volatility", N_SECTORS * (N_RETURN_DAYS - ROLLING_WINDOW + 1)),
        ("ticker_risk_return", N_TICKERS * N_PERIODS),
        ("sector_risk_return", N_SECTORS * N_PERIODS),
        ("ticker_correlation", N_TICKERS**2),
        ("sector_correlation", N_SECTORS**2),
    ],
)
def test_view_row_counts(con, view, expected):
    assert scalar(con, f"SELECT COUNT(*) FROM {view}") == expected


def test_ticker_daily_has_one_null_return_per_ticker(con):
    # Only each ticker's first date lacks a prior close.
    assert scalar(con, "SELECT COUNT(*) FROM ticker_daily_returns WHERE daily_return IS NULL") == N_TICKERS
    assert scalar(con, "SELECT COUNT(*) FROM ticker_daily_returns WHERE daily_return IS NOT NULL") == (
        N_TICKERS * N_RETURN_DAYS
    )


def test_no_duplicate_ticker_dates(con):
    assert scalar(
        con, "SELECT COUNT(*) FROM (SELECT ticker, trade_date FROM prices GROUP BY ALL HAVING COUNT(*) > 1)"
    ) == 0


def test_sector_mapping_matches_supplied_mapping(con):
    rows = con.execute("SELECT sector, ticker FROM sector_map").fetchall()
    actual = {}
    for sector, ticker in rows:
        actual.setdefault(sector, set()).add(ticker)
    assert actual == EXPECTED_SECTORS


def test_every_price_row_has_a_sector(con):
    assert scalar(con, "SELECT COUNT(*) FROM prices") == scalar(con, "SELECT COUNT(*) FROM raw_prices")


def test_dates_are_not_timezone_shifted(con):
    # The raw file stores UTC midnight; parsing must keep the calendar date.
    assert str(scalar(con, "SELECT MIN(trade_date) FROM prices")) == "2020-01-02"
    assert str(scalar(con, "SELECT MAX(trade_date) FROM prices")) == "2024-12-30"


@pytest.mark.parametrize(
    "view",
    ["ticker_risk_return", "sector_risk_return", "ticker_correlation", "sector_correlation",
     "sector_daily_returns", "sector_cumulative_returns", "ticker_rolling_volatility", "sector_rolling_volatility"],
)
def test_views_have_no_nulls(con, view):
    assert null_counts(con, f"SELECT * FROM {view}") == {}


def test_null_check_detects_partial_nulls(con):
    # Guards against COLUMNS(*)-in-WHERE semantics, which only match rows where every column is null.
    assert null_counts(con, "SELECT 1 AS a, NULL AS b UNION ALL SELECT 2, 3") == {"b": 1}


# ---------------------------------------------------------------- returns

def test_aapl_first_daily_return_matches_raw_closes(con):
    close_0, close_1 = [
        r[0] for r in con.execute(
            "SELECT close FROM raw_prices WHERE ticker = 'AAPL' ORDER BY trade_date LIMIT 2"
        ).fetchall()
    ]
    ret = scalar(
        con, "SELECT daily_return FROM ticker_daily_returns WHERE ticker = 'AAPL' AND trade_date = '2020-01-03'"
    )
    assert ret == pytest.approx(close_1 / close_0 - 1, abs=1e-12)


def test_aapl_full_period_return_matches_raw_closes(con):
    direct = scalar(
        con,
        "SELECT ARG_MAX(close, trade_date) / ARG_MIN(close, trade_date) - 1 FROM raw_prices WHERE ticker = 'AAPL'",
    )
    from_view = scalar(
        con, "SELECT total_return FROM ticker_risk_return WHERE ticker = 'AAPL' AND period = 'Full period'"
    )
    assert from_view == pytest.approx(direct, abs=1e-12)
    assert from_view > 0


def test_aapl_2022_return_matches_raw_closes(con):
    direct = scalar(
        con,
        """
        SELECT (SELECT ARG_MAX(close, trade_date) FROM raw_prices WHERE ticker = 'AAPL' AND year(trade_date) = 2022)
             / (SELECT ARG_MAX(close, trade_date) FROM raw_prices WHERE ticker = 'AAPL' AND year(trade_date) = 2021) - 1
        """,
    )
    from_view = scalar(con, "SELECT total_return FROM ticker_risk_return WHERE ticker = 'AAPL' AND period = '2022'")
    assert from_view == pytest.approx(direct, abs=1e-12)
    assert from_view < 0  # AAPL fell in 2022


def test_cumulative_return_matches_close_ratio(con):
    worst = scalar(
        con,
        """
        SELECT MAX(abs(t.cumulative_return - (p.close / f.first_close - 1)))
        FROM ticker_daily_returns t
        JOIN raw_prices p USING (ticker, trade_date)
        JOIN (SELECT ticker, ARG_MIN(close, trade_date) AS first_close FROM raw_prices GROUP BY ticker) f USING (ticker)
        """,
    )
    assert worst < 1e-9


def test_yearly_returns_compound_to_full_period(con):
    worst = scalar(
        con,
        """
        SELECT MAX(abs(f.total_return - y.compounded)) FROM
            (SELECT entity_type, entity, total_return FROM entity_period_risk_return WHERE period_type = 'full') f
        JOIN
            (SELECT entity_type, entity, product(1 + total_return) - 1 AS compounded
             FROM entity_period_risk_return WHERE period_type = 'year' GROUP BY ALL) y
        USING (entity_type, entity)
        """,
    )
    assert worst < 1e-9


def test_sector_daily_return_is_equal_weighted_mean(con):
    worst = scalar(
        con,
        """
        SELECT MAX(abs(s.daily_return - t.mean_return)) FROM sector_daily_returns s
        JOIN (SELECT trade_date, sector, AVG(daily_return) AS mean_return
              FROM ticker_daily_returns WHERE daily_return IS NOT NULL GROUP BY ALL) t
        USING (trade_date, sector)
        """,
    )
    assert worst < 1e-12


def test_sector_cumulative_matches_risk_return_total(con):
    worst = scalar(
        con,
        """
        SELECT MAX(abs(c.final - r.total_return)) FROM
            (SELECT sector, ARG_MAX(cumulative_return, trade_date) AS final FROM sector_cumulative_returns GROUP BY sector) c
        JOIN sector_risk_return r USING (sector)
        WHERE r.period = 'Full period'
        """,
    )
    assert worst < 1e-9


def test_known_directional_facts(con):
    def total(entity, period="Full period"):
        return scalar(
            con,
            "SELECT total_return FROM entity_period_risk_return WHERE entity = ? AND period = ?",
            [entity, period],
        )

    assert total("NVDA") > total("AAPL") > 0  # NVDA was the standout performer
    assert total("JNJ") < 0  # JNJ's price ended slightly below its 2020-01-02 close
    assert total("Energy", "2022") > 0 > total("Technology", "2022")


def test_risk_metrics_are_in_valid_ranges(con):
    assert scalar(con, "SELECT MIN(annualized_volatility) FROM entity_period_risk_return") > 0
    assert scalar(con, "SELECT MAX(max_drawdown) FROM entity_period_risk_return") <= 0
    assert scalar(con, "SELECT MIN(rolling_vol_30d) FROM ticker_rolling_volatility") > 0


def test_annualization_is_consistent(con):
    row = con.execute(
        "SELECT total_return, annualized_return, n_return_days FROM ticker_risk_return "
        "WHERE ticker = 'MSFT' AND period = 'Full period'"
    ).fetchone()
    total, annualized, n = row
    assert annualized == pytest.approx((1 + total) ** (252 / n) - 1)


# ---------------------------------------------------------------- correlation

@pytest.mark.parametrize("view, key", [("ticker_correlation", "ticker"), ("sector_correlation", "sector")])
def test_correlation_matrix_properties(con, view, key):
    assert scalar(con, f"SELECT COUNT(*) FROM {view} WHERE {key}_a = {key}_b AND correlation <> 1") == 0
    assert scalar(con, f"SELECT COUNT(*) FROM {view} WHERE correlation < -1 OR correlation > 1") == 0
    asymmetry = scalar(
        con,
        f"SELECT MAX(abs(x.correlation - y.correlation)) FROM {view} x "
        f"JOIN {view} y ON x.{key}_a = y.{key}_b AND x.{key}_b = y.{key}_a",
    )
    assert math.isclose(asymmetry, 0, abs_tol=1e-12)
