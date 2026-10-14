-- 01_base_views.sql
-- Load raw prices and the sector seed, and expose a joined base view.
-- Requires DuckDB variables (set by src/build_db.py):
--   raw_csv_path      path to data/raw/Stock Portfolio.csv
--   sector_seed_path  path to sql/seed_sector_mapping.csv

-- Date is read as text: the file stores UTC-midnight timestamps
-- ("2020-01-02 00:00:00+00:00"), and parsing them as TIMESTAMPTZ shifts
-- them into the session's local timezone. The first 10 chars are the trading date.
CREATE OR REPLACE TABLE raw_prices AS
SELECT
    CAST(substr("Date", 1, 10) AS DATE) AS trade_date,
    "Ticker"                            AS ticker,
    "Open"                              AS open,
    "High"                              AS high,
    "Low"                               AS low,
    "Close"                             AS close,
    "Volume"                            AS volume
FROM read_csv(getvariable('raw_csv_path'), header = true, types = {'Date': 'VARCHAR'});

CREATE OR REPLACE TABLE sector_map AS
SELECT ticker, sector
FROM read_csv(getvariable('sector_seed_path'), header = true,
              columns = {'ticker': 'VARCHAR', 'sector': 'VARCHAR'});

-- Inner join: a ticker missing from the seed would drop out, so
-- src/build_db.py checks every ticker in raw_prices has a sector.
CREATE OR REPLACE VIEW prices AS
SELECT p.trade_date, p.ticker, s.sector, p.open, p.high, p.low, p.close, p.volume
FROM raw_prices p
JOIN sector_map s USING (ticker);
