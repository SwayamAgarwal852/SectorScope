# SectorScope

Sector-wise performance and risk-return analysis of 21 S&P 500 companies (2020–2024), built on DuckDB, with a Streamlit portfolio comparison tool.

> Full project documentation is in progress.

## Data

Source: [Market Champions: Leading Stocks Dataset](https://www.kaggle.com/datasets/jijagallery/industry-leaders-performance-dataset) by jijagallery on Kaggle — daily OHLCV for 21 companies, stored at `data/raw/Stock Portfolio.csv`.

- **Prices are split-adjusted but not dividend-adjusted** (no adjusted-close column), so all returns in this project are price returns, not total returns.
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

### Sector weighting

Sector returns are **equal-weighted** averages of their constituents' daily returns. The dataset contains no market-cap or shares-outstanding data, so cap-weighting is not possible without importing an external source, which this project deliberately avoids. Note that Cloud/Software, Energy and Industrials have only two constituents each, so their sector figures are heavily driven by individual stocks.
