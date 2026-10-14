# SectorScope

Sector-wise performance and risk-return analysis of 21 S&P 500 companies (2020–2024), built on DuckDB, with a Streamlit portfolio comparison tool.

> Full project documentation is in progress.

## Data

Source: [Market Champions: Leading Stocks Dataset](https://www.kaggle.com/datasets/jijagallery/industry-leaders-performance-dataset) by jijagallery on Kaggle — daily OHLCV for 21 companies, stored at `data/raw/Stock Portfolio.csv`.

- **Prices are split-adjusted but not dividend-adjusted** (no adjusted-close column), so all returns in this project are price returns, not total returns.
- The file ends on 2024-12-30; 2024-12-31 is not included.

### Sector mapping (manually supplied)

The dataset ships **without sector labels**. The ticker→sector mapping in [`sql/seed_sector_mapping.csv`](sql/seed_sector_mapping.csv) is a GICS-style classification supplied manually for this project; it is not sourced from the original dataset. It uses **8 sectors**, although the dataset's description lists 7: NextEra Energy (NEE) is a utility and is kept in its own Utilities sector rather than forced into Energy.

| Sector | Tickers |
|---|---|
| Technology | AAPL, GOOGL, MSFT, NVDA, ASML, TSM |
| Cloud/Software | CRM |
| Healthcare | JNJ, LLY, UNH |
| Financials | JPM, BLK, V |
| Consumer | AMZN, COST, PG, WMT |
| Industrials | CAT, HON |
| Energy | XOM |
| Utilities | NEE |

### Sector weighting

Sector returns are **equal-weighted** averages of their constituents' daily returns. The dataset contains no market-cap or shares-outstanding data, so cap-weighting is not possible without importing an external source, which this project deliberately avoids. Note that several sectors have only one or two constituents (Cloud/Software, Energy, Utilities, Industrials), so their "sector" figures reflect individual stocks.
