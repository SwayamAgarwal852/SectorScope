"""Portfolio analytics on top of the SectorScope DuckDB views.

Used by the Streamlit app. All computation runs in DuckDB against the views
built by src/build_db.py; pandas is only the return type.

Weights are passed as parallel ticker / weight lists and must sum to 1.
Two rebalancing modes are supported:
  buy_and_hold  weights are set on 2020-01-02 and then drift with prices
  daily         weights are reset every day (constant-weight portfolio),
                the same convention the equal-weighted sector figures use
"""

from pathlib import Path

import duckdb
import pandas as pd

from build_db import DB_PATH, RAW_CSV, SECTOR_SEED, build, sql_files

REBALANCE_MODES = ("buy_and_hold", "daily")

_WEIGHTS_CTE = "weights AS (SELECT unnest(?::VARCHAR[]) AS ticker, unnest(?::DOUBLE[]) AS weight)"

# One row per trading date from 2020-01-02. daily_return is NULL on the
# first date; cumulative_return is 0 there.
_SERIES_SQL = {
    "buy_and_hold": f"""
        WITH {_WEIGHTS_CTE},
        value AS (
            SELECT t.trade_date, SUM(w.weight * (1 + t.cumulative_return)) AS growth
            FROM ticker_daily_returns t
            JOIN weights w USING (ticker)
            GROUP BY t.trade_date
        )
        SELECT
            trade_date,
            growth / LAG(growth) OVER (ORDER BY trade_date) - 1 AS daily_return,
            growth - 1                                          AS cumulative_return
        FROM value
    """,
    "daily": f"""
        WITH {_WEIGHTS_CTE},
        daily AS (
            SELECT t.trade_date, SUM(w.weight * t.daily_return) AS daily_return
            FROM ticker_daily_returns t
            JOIN weights w USING (ticker)
            GROUP BY t.trade_date
        )
        SELECT
            trade_date,
            daily_return,
            COALESCE(exp(SUM(ln(1 + daily_return)) OVER (ORDER BY trade_date)) - 1, 0) AS cumulative_return
        FROM daily
    """,
}

# Same metric definitions as sql/04_risk_return.sql (full period).
_METRICS_SQL = """
    WITH series AS ({series_sql}),
    path AS (
        SELECT
            trade_date,
            daily_return,
            1 + cumulative_return AS growth,
            MAX(1 + cumulative_return) OVER (ORDER BY trade_date) AS peak
        FROM series
    ),
    stats AS (
        SELECT
            COUNT(daily_return)                                   AS n_return_days,
            ARG_MAX(growth, trade_date) - 1                       AS total_return,
            STDDEV_SAMP(daily_return) * sqrt(252)                 AS annualized_volatility,
            MIN(growth / GREATEST(1, peak) - 1)                   AS max_drawdown
        FROM path
    )
    SELECT
        n_return_days,
        total_return,
        pow(1 + total_return, 252.0 / n_return_days) - 1                          AS annualized_return,
        annualized_volatility,
        (pow(1 + total_return, 252.0 / n_return_days) - 1) / annualized_volatility AS return_to_risk,
        max_drawdown
    FROM stats
"""


def _db_is_stale(db_path: Path) -> bool:
    if not db_path.exists():
        return True
    built_at = db_path.stat().st_mtime
    sources = [RAW_CSV, SECTOR_SEED, *sql_files()]
    return any(p.stat().st_mtime > built_at for p in sources)


def connect(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Open the analytics database read-only, (re)building it first if it is
    missing or older than the raw data / SQL files."""
    if _db_is_stale(db_path):
        build(db_path)
    return duckdb.connect(str(db_path), read_only=True)


def _validate(tickers: list[str], weights: list[float], rebalance: str) -> None:
    if rebalance not in REBALANCE_MODES:
        raise ValueError(f"rebalance must be one of {REBALANCE_MODES}, got {rebalance!r}")
    if not tickers or len(tickers) != len(weights):
        raise ValueError("tickers and weights must be non-empty and the same length")
    if len(set(tickers)) != len(tickers):
        raise ValueError("tickers must be unique")
    if any(w < 0 for w in weights) or abs(sum(weights) - 1) > 1e-9:
        raise ValueError("weights must be non-negative and sum to 1")


def portfolio_series(
    con: duckdb.DuckDBPyConnection, tickers: list[str], weights: list[float], rebalance: str
) -> pd.DataFrame:
    """Daily and cumulative return of the weighted portfolio."""
    _validate(tickers, weights, rebalance)
    return con.execute(
        _SERIES_SQL[rebalance] + " ORDER BY trade_date", [list(tickers), list(weights)]
    ).df()


def portfolio_metrics(
    con: duckdb.DuckDBPyConnection, tickers: list[str], weights: list[float], rebalance: str
) -> dict[str, float]:
    """Full-period risk-return metrics, defined as in sql/04_risk_return.sql."""
    _validate(tickers, weights, rebalance)
    sql = _METRICS_SQL.format(series_sql=_SERIES_SQL[rebalance])
    row = con.execute(sql, [list(tickers), list(weights)]).df().iloc[0]
    return row.to_dict()


def sector_weights(
    con: duckdb.DuckDBPyConnection, tickers: list[str], weights: list[float], rebalance: str
) -> pd.DataFrame:
    """Starting and current (last-date) weight per sector.

    Under buy and hold each holding's current weight is its starting weight
    grown by its cumulative return, renormalized; under daily rebalancing
    weights are reset every day, so current equals starting.
    """
    _validate(tickers, weights, rebalance)
    return con.execute(
        f"""
        WITH {_WEIGHTS_CTE},
        last_growth AS (
            SELECT ticker, sector, ARG_MAX(1 + cumulative_return, trade_date) AS growth
            FROM ticker_daily_returns
            GROUP BY ticker, sector
        ),
        holdings AS (
            SELECT
                g.sector,
                g.ticker,
                w.weight AS starting_weight,
                CASE WHEN ? = 'buy_and_hold' THEN w.weight * g.growth ELSE w.weight END AS current_value
            FROM weights w
            JOIN last_growth g USING (ticker)
        )
        SELECT
            sector,
            string_agg(ticker, ', ' ORDER BY ticker)        AS tickers,
            SUM(starting_weight)                            AS starting_weight,
            SUM(current_value) / SUM(SUM(current_value)) OVER () AS current_weight
        FROM holdings
        GROUP BY sector
        ORDER BY current_weight, sector
        """,
        [list(tickers), list(weights), rebalance],
    ).df()


def tickers(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """All tickers with their sector, ordered by sector then ticker."""
    return con.execute("SELECT ticker, sector FROM sector_map ORDER BY sector, ticker").df()


def ticker_full_period(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Full-period risk-return row per ticker."""
    return con.execute(
        """
        SELECT ticker, sector, total_return, annualized_return, annualized_volatility,
               return_to_risk, max_drawdown
        FROM ticker_risk_return
        WHERE period_type = 'full'
        ORDER BY ticker
        """
    ).df()


def ticker_cumulative(con: duckdb.DuckDBPyConnection, selected: list[str]) -> pd.DataFrame:
    """Daily cumulative return per selected ticker (long format)."""
    return con.execute(
        """
        SELECT trade_date, ticker, cumulative_return
        FROM ticker_daily_returns
        WHERE list_contains(?, ticker)
        ORDER BY ticker, trade_date
        """,
        [list(selected)],
    ).df()


def correlation_matrix(con: duckdb.DuckDBPyConnection, selected: list[str]) -> pd.DataFrame:
    """Square correlation matrix of daily returns for the selected tickers,
    rows and columns ordered by sector then ticker."""
    long = con.execute(
        """
        SELECT ticker_a, ticker_b, correlation
        FROM ticker_correlation
        WHERE list_contains(?, ticker_a) AND list_contains(?, ticker_b)
        ORDER BY sector_a, ticker_a, sector_b, ticker_b
        """,
        [list(selected), list(selected)],
    ).df()
    order = list(dict.fromkeys(long["ticker_a"]))
    return long.pivot(index="ticker_a", columns="ticker_b", values="correlation").loc[order, order]
