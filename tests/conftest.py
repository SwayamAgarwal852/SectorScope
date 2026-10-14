import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_db  # noqa: E402
import export_powerbi  # noqa: E402

# Shape of the raw file, verified in Phase 1.
N_TICKERS = 21
N_SECTORS = 7
N_DATES = 1257
N_RETURN_DAYS = N_DATES - 1
ROLLING_WINDOW = 30
N_PERIODS = 6  # Full period + 2020..2024

# Manually supplied mapping (matches the dataset's 7 described categories).
EXPECTED_SECTORS = {
    "Technology": {"AAPL", "GOOGL", "MSFT", "NVDA", "TSM"},
    "Cloud/Software": {"CRM", "ASML"},
    "Healthcare": {"JNJ", "LLY", "UNH"},
    "Financials": {"JPM", "BLK", "V"},
    "Consumer": {"AMZN", "COST", "PG", "WMT"},
    "Industrials": {"CAT", "HON"},
    "Energy": {"XOM", "NEE"},
}


@pytest.fixture(scope="session")
def db_path(tmp_path_factory) -> Path:
    """A freshly built database in a temp dir, so tests never touch data/processed/."""
    return build_db.build(tmp_path_factory.mktemp("db") / "test.duckdb")


@pytest.fixture(scope="session")
def con(db_path):
    with duckdb.connect(str(db_path), read_only=True) as c:
        yield c


@pytest.fixture(scope="session")
def export_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("exports")
    export_powerbi.export(export_dir=out, db_path=out / "export.duckdb")
    return out


def scalar(con, sql: str, params=None):
    return con.execute(sql, params or []).fetchone()[0]
