"""Export flat CSV tables from the DuckDB views for Power BI.

Rebuilds the database first so exports always reflect the current sql/ layer,
then writes one CSV per table to exports/. Refuses to write a table that
contains nulls. Column meanings are documented in exports/README.md.

Usage:
    python src/export_powerbi.py
"""

from pathlib import Path

import duckdb

from build_db import ROOT, build

EXPORT_DIR = ROOT / "exports"

EXPORTS = {
    "ticker_daily.csv": """
        SELECT trade_date, ticker, sector, close, volume, daily_return, log_return, cumulative_return
        FROM ticker_daily_returns
        WHERE daily_return IS NOT NULL
        ORDER BY ticker, trade_date
    """,
    "sector_daily.csv": """
        SELECT trade_date, sector, n_constituents, daily_return, cumulative_return
        FROM sector_cumulative_returns
        ORDER BY sector, trade_date
    """,
    "sector_summary.csv": """
        SELECT *
        FROM sector_risk_return
        ORDER BY sector, period_type, period
    """,
    "ticker_risk_return.csv": """
        SELECT *
        FROM ticker_risk_return
        ORDER BY ticker, period_type, period
    """,
    "correlation.csv": """
        SELECT ticker_a, sector_a, ticker_b, sector_b, correlation, n_obs
        FROM ticker_correlation
        ORDER BY ticker_a, ticker_b
    """,
    "sector_correlation.csv": """
        SELECT sector_a, sector_b, correlation, n_obs
        FROM sector_correlation
        ORDER BY sector_a, sector_b
    """,
    "ticker_rolling_volatility.csv": """
        SELECT trade_date, ticker, sector, rolling_vol_30d, rolling_vol_30d_annualized
        FROM ticker_rolling_volatility
        ORDER BY ticker, trade_date
    """,
    "sector_rolling_volatility.csv": """
        SELECT trade_date, sector, rolling_vol_30d, rolling_vol_30d_annualized
        FROM sector_rolling_volatility
        ORDER BY sector, trade_date
    """,
}


def export(export_dir: Path = EXPORT_DIR) -> dict[str, int]:
    db_path = build()
    export_dir.mkdir(parents=True, exist_ok=True)
    row_counts = {}
    with duckdb.connect(str(db_path), read_only=True) as con:
        for filename, query in EXPORTS.items():
            rel = con.sql(query)
            null_rows = con.sql(
                f"SELECT COUNT(*) FROM ({query}) WHERE NOT (COLUMNS(*) IS NOT NULL)"
            ).fetchone()[0]
            if null_rows:
                raise ValueError(f"{filename}: {null_rows} rows contain nulls; not exporting")
            out = export_dir / filename
            rel.write_csv(str(out), header=True, date_format="%Y-%m-%d")
            row_counts[filename] = con.sql(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]
    return row_counts


if __name__ == "__main__":
    for name, n in export().items():
        print(f"exports/{name:32s} {n:>7,} rows")
