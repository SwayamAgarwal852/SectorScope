"""Build the SectorScope DuckDB database from the raw CSV and the sql/ layer.

Runs every numbered sql/NN_*.sql file in order against
data/processed/sectorscope.duckdb, replacing its tables and views.

Usage:
    python src/build_db.py
"""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
RAW_CSV = ROOT / "data" / "raw" / "Stock Portfolio.csv"
SECTOR_SEED = SQL_DIR / "seed_sector_mapping.csv"
DB_PATH = ROOT / "data" / "processed" / "sectorscope.duckdb"


def sql_files() -> list[Path]:
    return sorted(p for p in SQL_DIR.glob("[0-9][0-9]_*.sql"))


def build(db_path: Path = DB_PATH) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("SET VARIABLE raw_csv_path = ?", [str(RAW_CSV)])
        con.execute("SET VARIABLE sector_seed_path = ?", [str(SECTOR_SEED)])
        for path in sql_files():
            con.execute(path.read_text(encoding="utf-8"))

        unmapped = con.execute(
            "SELECT DISTINCT ticker FROM raw_prices "
            "WHERE ticker NOT IN (SELECT ticker FROM sector_map) ORDER BY ticker"
        ).fetchall()
        if unmapped:
            raise ValueError(f"Tickers missing from {SECTOR_SEED.name}: {[t for (t,) in unmapped]}")
    return db_path


if __name__ == "__main__":
    path = build()
    print(f"Built {path.relative_to(ROOT)} from {len(sql_files())} SQL files")
