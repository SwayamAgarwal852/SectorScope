# SectorScope

Sector-wise performance and risk-return analysis of 21 S&P 500 companies across 7 sectors, using daily prices from 2020 to 2024.

The core of the project is a **DuckDB SQL analytics layer** that turns raw daily prices into returns, rolling volatility, equal-weighted sector indices, risk-return summaries and correlation matrices. On top of it sit:

- **Power BI-ready CSV exports** for a sector dashboard (built separately in Power BI Desktop), and
- a **Streamlit portfolio comparison app**, where you pick holdings and weights and see the portfolio's historical return, volatility, drawdown, sector mix and correlation structure in interactive Plotly charts.

All analysis is **historical and descriptive**. Nothing in this project forecasts prices or gives investment advice.

## Key findings (2020-01-02 to 2024-12-30)

Equal-weighted sectors, price returns, full period:

| Sector | Annualized return | Annualized volatility | Return / risk | Max drawdown |
|---|---:|---:|---:|---:|
| Technology | 38.7% | 31.3% | 1.24 | -42.3% |
| Consumer | 18.9% | 19.7% | 0.96 | -25.1% |
| Healthcare | 18.4% | 21.7% | 0.85 | -26.8% |
| Cloud/Software | 19.1% | 36.3% | 0.53 | -54.2% |
| Financials | 13.5% | 26.8% | 0.50 | -40.4% |
| Industrials | 12.7% | 26.9% | 0.47 | -40.5% |
| Energy | 8.1% | 26.0% | 0.31 | -42.6% |

- **Technology led on both return and risk-adjusted return**, and was the top sector in every year except 2022.
- **2022 flipped the ranking:** Energy led (+29.9%) while Cloud/Software (-39.0%) and Technology (-35.7%) fell hardest.
- **Consumer and Healthcare were the defensive pair:** returns close to 19% a year with the lowest volatility and the shallowest drawdowns.
- **Diversification:** Cloud/Software and Technology moved closely together (correlation 0.81), while Cloud/Software–Healthcare (0.37) and Cloud/Software–Energy (0.39) were the least correlated sector pairs.

Several sectors have only 2 constituents, so treat those sector figures as small-sample (see [Sector weighting](#sector-weighting)).

## Project structure

```
SectorScope/
├── data/
│   ├── raw/Stock Portfolio.csv      # source data (CC0), committed
│   └── processed/                   # sectorscope.duckdb, built locally (gitignored)
├── sql/
│   ├── seed_sector_mapping.csv      # ticker → sector (manually supplied)
│   ├── 01_base_views.sql            # load prices + sector map, joined base view
│   ├── 02_returns.sql               # daily / log / cumulative returns, rolling volatility per ticker
│   ├── 03_sector_aggregates.sql     # equal-weighted sector returns and rolling volatility
│   ├── 04_risk_return.sql           # full-period and yearly risk-return summary
│   └── 05_correlation.sql           # ticker and sector correlation matrices
├── src/
│   ├── validate_data.py             # read-only checks on the raw CSV
│   ├── build_db.py                  # builds the DuckDB database from sql/
│   ├── export_powerbi.py            # writes the Power BI CSVs to exports/
│   └── portfolio.py                 # portfolio analytics used by the app
├── streamlit_app/app.py             # portfolio comparison app
├── exports/README.md                # data dictionary for the Power BI CSVs (CSVs gitignored)
├── tests/                           # pytest suite
├── requirements.txt                 # runtime dependencies (also used by Streamlit Cloud)
└── requirements-dev.txt             # runtime + pytest
```

## Setup

Requires Python 3.11+ (pandas 3 needs it; developed on 3.13).

```bash
git clone https://github.com/SwayamAgarwal852/SectorScope.git
cd SectorScope
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt   # or requirements.txt if you don't need to run tests
```

- `requirements.txt`: what the app needs to run (duckdb, pandas, streamlit, plotly). Streamlit Community Cloud installs this file.
- `requirements-dev.txt`: everything in `requirements.txt` plus pytest.

## Usage

Run all commands from the repository root.

| Step | Command | What it does |
|---|---|---|
| Validate | `python src/validate_data.py` | Checks the raw CSV for schema, nulls, duplicate (ticker, date) pairs, date gaps and price sanity. Read-only; exits non-zero on failure. |
| Build | `python src/build_db.py` | Recreates `data/processed/sectorscope.duckdb` by running `sql/01`–`05` in order. |
| Export | `python src/export_powerbi.py` | Rebuilds the database, then writes 8 CSVs to `exports/` for Power BI. Refuses to write any table containing nulls. |
| App | `streamlit run streamlit_app/app.py` | Starts the portfolio comparison app at http://localhost:8501. |
| Test | `pytest` | Runs the test suite (builds its own database and exports in a temp directory). |

You don't need to run the build step before the app: it builds the database automatically if it's missing or older than the raw data and SQL files.

## Methodology

- **Returns** are close-to-close **price returns**. The source prices are split-adjusted but not dividend-adjusted, so dividends are excluded.
- **Annualization** uses 252 trading days. Annualized return is the CAGR, `(1 + total_return) ^ (252 / n_days) - 1`; annualized volatility is the sample standard deviation of daily returns × √252.
- **Return / risk** is annualized return ÷ annualized volatility: a Sharpe-style ratio with a 0% risk-free rate, because the data has no risk-free series.
- **Max drawdown** is the worst peak-to-trough fall of the cumulative value within the period.
- **Rolling volatility** uses a 30-trading-day window and is only reported once a full window exists.
- **Correlation** is the Pearson correlation of daily returns over the full period.
- **Yearly figures** measure each calendar year from the last close of the previous year.

### Sector weighting

Sector returns are **equal-weighted** averages of their constituents' daily returns (equal weights, rebalanced daily). The dataset contains no market-cap or shares-outstanding data, so cap-weighting is not possible without importing an external source, which this project deliberately avoids. Note that Cloud/Software, Energy and Industrials have only two constituents each, so their sector figures are heavily driven by individual stocks.

### Portfolio app

The app offers two rebalancing modes, and they can give very different results:

- **Buy and hold** (default): weights are set on 2020-01-02 and then drift with prices.
- **Daily rebalance**: weights are reset to target every day, the same convention as the sector figures.

Under buy and hold, the sector breakdown shows each sector's **starting** weight next to its **current** weight on the last date (starting weight × the holdings' growth, renormalized), so the drift is visible. Under daily rebalancing the two are identical by definition, so only the target weights are shown.

Every portfolio is compared with a benchmark of all 21 stocks, equally weighted, using the same rebalancing mode. The test suite checks that a 100% single-stock portfolio reproduces that stock's figures from the SQL layer, and that an equal-weight, daily-rebalanced portfolio of a sector's stocks reproduces that sector's figures.

## SQL layer

`src/build_db.py` runs the numbered files in `sql/` in order against a fresh DuckDB database. Each file builds on the views from the previous ones:

| File | Objects | Purpose |
|---|---|---|
| `01_base_views.sql` | `raw_prices`, `sector_map`, `prices` | Load the raw CSV (dates parsed from the text so the UTC timestamps aren't shifted into local time) and the sector seed, then join them |
| `02_returns.sql` | `ticker_daily_returns`, `ticker_rolling_volatility` | Daily, log and cumulative returns; 30-day rolling volatility per ticker |
| `03_sector_aggregates.sql` | `sector_daily_returns`, `sector_cumulative_returns`, `sector_rolling_volatility` | Equal-weighted sector index and its rolling volatility |
| `04_risk_return.sql` | `entity_daily_returns`, `entity_period_risk_return`, `ticker_risk_return`, `sector_risk_return` | Total and annualized return, volatility, return/risk and max drawdown per ticker and sector, for the full period and each year |
| `05_correlation.sql` | `ticker_correlation`, `sector_correlation` | Pairwise correlation matrices in long format |

The raw and seed file paths are passed in as DuckDB variables (`raw_csv_path`, `sector_seed_path`), so the SQL files contain no hard-coded paths.

## Power BI

The Power BI dashboard is built separately in Power BI Desktop from the CSVs in `exports/`. **The CSVs are not committed**: regenerate them locally before a Power BI session (and after any data or SQL change):

```bash
python src/export_powerbi.py
```

This writes 8 CSVs to `exports/`. See [`exports/README.md`](exports/README.md) for every file's columns, grain and conventions.

> Power BI dashboard: *to be added. The report file and screenshots will be linked here once built.*

## Data

Source: [Market Champions: Leading Stocks Dataset](https://www.kaggle.com/datasets/jijagallery/industry-leaders-performance-dataset) by jijagallery on Kaggle, released under **CC0: Public Domain**. It contains daily OHLCV data for 21 companies, stored at `data/raw/Stock Portfolio.csv`.

- **Prices are split-adjusted but not dividend-adjusted** (there is no adjusted-close column), so all returns in this project are price returns, not total returns.
- The file ends on 2024-12-30; 2024-12-31 is not included.

### Sector mapping (manually supplied)

The CSV itself has **no sector column**. The ticker→sector mapping in [`sql/seed_sector_mapping.csv`](sql/seed_sector_mapping.csv) was entered manually and follows the **7 sector categories described on the dataset's Kaggle page**. Some of these differ from a GICS classification: ASML (semiconductor equipment) sits in Cloud/Software, and NextEra Energy (NEE, a utility) sits in Energy.

| Sector | Tickers |
|---|---|
| Technology | AAPL, GOOGL, MSFT, NVDA, TSM |
| Cloud/Software | CRM, ASML |
| Healthcare | JNJ, LLY, UNH |
| Financials | JPM, BLK, V |
| Consumer | AMZN, COST, PG, WMT |
| Industrials | CAT, HON |
| Energy | XOM, NEE |

## Limitations

- **Price returns only:** dividends are excluded, which understates the total return of dividend-paying stocks.
- **Small sectors:** three sectors have only two stocks, so their figures say more about those stocks than about the sector as a whole.
- **Selection bias:** the dataset describes these 21 companies as market leaders, a choice made with hindsight, so the universe leans toward stocks that did well.
- **Backward-looking:** volatility and correlation describe 2020–2024 and are not estimates of future risk.
