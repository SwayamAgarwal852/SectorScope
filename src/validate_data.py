"""Validate the raw price file before it feeds the SQL layer.

Read-only: reports findings and exits non-zero on hard failures. Nothing is
modified or dropped.

Usage:
    python src/validate_data.py
"""

import sys
from pathlib import Path

import duckdb

RAW_CSV = Path(__file__).resolve().parents[1] / "data" / "raw" / "Stock Portfolio.csv"
EXPECTED_COLUMNS = ["Date", "Ticker", "Open", "High", "Low", "Close", "Volume"]
# Flag daily close-to-close moves larger than this for manual review.
EXTREME_MOVE = 0.25
# Longest gap (calendar days) between trading dates before we flag it.
MAX_GAP_DAYS = 4


def load(con: duckdb.DuckDBPyConnection) -> None:
    # Date is read as text: the file stores UTC-midnight timestamps
    # ("2020-01-02 00:00:00+00:00"), and parsing them as TIMESTAMPTZ shifts
    # them into the local timezone. The first 10 chars are the trading date.
    con.execute(
        "CREATE TABLE raw AS SELECT * FROM read_csv(?, header = true, types = {'Date': 'VARCHAR'})",
        [str(RAW_CSV)],
    )
    con.execute(
        """
        CREATE TABLE prices AS
        SELECT CAST(substr(Date, 1, 10) AS DATE) AS trade_date,
               Ticker AS ticker, Open, High, Low, Close, Volume
        FROM raw
        """
    )


def main() -> int:
    if not RAW_CSV.exists():
        print(f"FAIL: raw file not found at {RAW_CSV}")
        return 1

    con = duckdb.connect()
    load(con)
    failures = []

    def scalar(sql: str):
        return con.execute(sql).fetchone()[0]

    # Schema
    columns = [r[0] for r in con.execute("DESCRIBE raw").fetchall()]
    print(f"Columns: {columns}")
    if columns != EXPECTED_COLUMNS:
        failures.append(f"unexpected columns {columns}")

    # Shape
    n_rows = scalar("SELECT COUNT(*) FROM prices")
    n_tickers = scalar("SELECT COUNT(DISTINCT ticker) FROM prices")
    min_d, max_d = con.execute("SELECT MIN(trade_date), MAX(trade_date) FROM prices").fetchone()
    print(f"Rows: {n_rows:,} | Tickers: {n_tickers} | Dates: {min_d} to {max_d}")

    # Date-string format: every row should be UTC midnight
    bad_ts = scalar("SELECT COUNT(*) FROM raw WHERE Date NOT LIKE '____-__-__ 00:00:00+00:00'")
    print(f"Non-UTC-midnight timestamps: {bad_ts}")
    if bad_ts:
        failures.append(f"{bad_ts} timestamps not in UTC-midnight format")

    # Nulls
    null_counts = con.execute(
        "SELECT " + ", ".join(f"COUNT(*) - COUNT({c})" for c in EXPECTED_COLUMNS) + " FROM raw"
    ).fetchone()
    nulls = {c: n for c, n in zip(EXPECTED_COLUMNS, null_counts) if n}
    print(f"Nulls: {nulls or 'none'}")
    if nulls:
        failures.append(f"nulls found {nulls}")

    # Duplicate (ticker, date)
    dupes = scalar(
        "SELECT COUNT(*) FROM (SELECT ticker, trade_date FROM prices GROUP BY ALL HAVING COUNT(*) > 1)"
    )
    print(f"Duplicate (ticker, date) pairs: {dupes}")
    if dupes:
        failures.append(f"{dupes} duplicate (ticker, date) pairs")

    # Per-ticker coverage: every ticker should trade on every date in the file
    n_dates = scalar("SELECT COUNT(DISTINCT trade_date) FROM prices")
    short = con.execute(
        "SELECT ticker, COUNT(*) FROM prices GROUP BY ticker HAVING COUNT(*) <> ? ORDER BY ticker",
        [n_dates],
    ).fetchall()
    print(f"Distinct trading dates: {n_dates} | Tickers missing dates: {short or 'none'}")
    if short:
        failures.append(f"tickers with incomplete date coverage {short}")

    # Date continuity: gaps longer than a long weekend
    gaps = con.execute(
        f"""
        SELECT prev_date, trade_date, trade_date - prev_date AS gap_days FROM (
            SELECT trade_date, LAG(trade_date) OVER (ORDER BY trade_date) AS prev_date
            FROM (SELECT DISTINCT trade_date FROM prices))
        WHERE trade_date - prev_date > {MAX_GAP_DAYS}
        """
    ).fetchall()
    print(f"Calendar gaps > {MAX_GAP_DAYS} days: {gaps or 'none'}")
    if gaps:
        failures.append(f"date gaps {gaps}")
    per_year = con.execute(
        "SELECT year(trade_date), COUNT(DISTINCT trade_date) FROM prices GROUP BY 1 ORDER BY 1"
    ).fetchall()
    print(f"Trading dates per year: {per_year}")

    # Price sanity
    bad_prices = scalar(
        "SELECT COUNT(*) FROM prices WHERE LEAST(Open, High, Low, Close) <= 0 OR Volume < 0"
    )
    bad_ohlc = scalar(
        "SELECT COUNT(*) FROM prices WHERE High < GREATEST(Open, Close, Low) OR Low > LEAST(Open, Close, High)"
    )
    print(f"Non-positive prices / negative volume: {bad_prices} | Inconsistent OHLC rows: {bad_ohlc}")
    if bad_prices:
        failures.append(f"{bad_prices} rows with non-positive price or negative volume")
    if bad_ohlc:
        print("  WARN: OHLC inconsistencies are reported only, not treated as failures")

    # Extreme moves (informational: may be real events or unadjusted splits)
    extremes = con.execute(
        f"""
        SELECT ticker, trade_date, ROUND(ret, 4) FROM (
            SELECT ticker, trade_date,
                   Close / LAG(Close) OVER (PARTITION BY ticker ORDER BY trade_date) - 1 AS ret
            FROM prices)
        WHERE abs(ret) > {EXTREME_MOVE} ORDER BY ticker, trade_date
        """
    ).fetchall()
    print(f"Daily moves > {EXTREME_MOVE:.0%} (review, not failures): {extremes or 'none'}")

    print()
    if failures:
        print("VALIDATION FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
