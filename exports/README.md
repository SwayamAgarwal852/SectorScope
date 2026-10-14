# Power BI exports

Flat CSV tables generated from the DuckDB SQL layer (`sql/`) for loading into Power BI Desktop. Regenerate them with:

```bash
python src/export_powerbi.py
```

The script rebuilds `data/processed/sectorscope.duckdb` from the raw CSV first, so the exports always match the current SQL. It will not write a file that contains nulls: every row only holds values that are actually defined.

## Conventions (all files)

- **Encoding / format:** UTF-8, comma-separated, header row, `.` as decimal separator.
- **Dates:** ISO `YYYY-MM-DD` (trading dates, US market calendar). Data covers 2020-01-02 to 2024-12-30.
- **Returns, volatility, drawdown** are **decimals**, not percentages: `0.05` = 5%, `-0.30` = -30%. Format them as percentages in Power BI.
- **Price returns only.** Prices are split-adjusted but not dividend-adjusted, so no return includes dividends.
- **Annualization** uses 252 trading days per year.
- **Sector** is one of 7 values from the manually supplied mapping in [`sql/seed_sector_mapping.csv`](../sql/seed_sector_mapping.csv): Technology, Cloud/Software, Healthcare, Financials, Consumer, Industrials, Energy.
- **Sector figures are equal-weighted:** a sector's daily return is the simple average of its constituents' daily returns (equal weights, rebalanced daily). See the main README for why.

## Files

| File | Grain (one row per) | Rows |
|---|---|---:|
| `ticker_daily.csv` | ticker × trading date | 26,376 |
| `sector_daily.csv` | sector × trading date | 8,792 |
| `sector_summary.csv` | sector × period | 42 |
| `ticker_risk_return.csv` | ticker × period | 126 |
| `correlation.csv` | ordered ticker pair | 441 |
| `ticker_rolling_volatility.csv` | ticker × trading date (full 30-day windows only) | 25,767 |
| `sector_rolling_volatility.csv` | sector × trading date (full 30-day windows only) | 8,589 |

---

### `ticker_daily.csv`

Daily prices and returns per stock. Starts on **2020-01-03**, the first date with a prior close to compute a return from (2020-01-02 is the base date).

| Column | Type | Meaning |
|---|---|---|
| `trade_date` | date | Trading date |
| `ticker` | text | Stock ticker (21 values) |
| `sector` | text | Sector of the ticker |
| `close` | decimal | Closing price (split-adjusted, USD) |
| `volume` | integer | Shares traded that day |
| `daily_return` | decimal | Close-to-close return vs. the previous trading day: `close / prev_close - 1` |
| `log_return` | decimal | `ln(close / prev_close)` |
| `cumulative_return` | decimal | Return since the first close on 2020-01-02: `close / first_close - 1` |

### `sector_daily.csv`

Daily equal-weighted sector index. Starts on 2020-01-03.

| Column | Type | Meaning |
|---|---|---|
| `trade_date` | date | Trading date |
| `sector` | text | Sector |
| `n_constituents` | integer | Number of tickers averaged that day |
| `daily_return` | decimal | Average of the constituents' `daily_return` |
| `cumulative_return` | decimal | Compounded growth of the sector index since 2020-01-02: product of `(1 + daily_return)` minus 1 |

> A sector's `cumulative_return` is **not** the average of its tickers' `cumulative_return`; it compounds the daily equal-weighted returns. Use this column for sector lines rather than averaging ticker cumulative returns in Power BI.

### `sector_summary.csv`

Risk-return summary per sector, for the full period and each calendar year. Filter on `period_type` / `period` so you don't mix full-period and yearly rows.

| Column | Type | Meaning |
|---|---|---|
| `sector` | text | Sector |
| `n_constituents` | integer | Number of tickers in the sector |
| `tickers` | text | Comma-separated list of the sector's tickers |
| `period_type` | text | `full` (whole 2020–2024 span) or `year` (one calendar year) |
| `period` | text | `Full period`, or the year as text: `2020` … `2024` |
| `period_start` | date | First trading date with a return in the period |
| `period_end` | date | Last trading date in the period |
| `n_return_days` | integer | Number of daily returns in the period |
| `total_return` | decimal | Compounded return over the period, measured from the last close **before** `period_start` (for 2020 and `Full period`, from the 2020-01-02 close) |
| `annualized_return` | decimal | CAGR: `(1 + total_return) ^ (252 / n_return_days) - 1`. For a single year this is close to `total_return` |
| `annualized_volatility` | decimal | Sample standard deviation of daily returns × √252 |
| `return_to_risk` | decimal | `annualized_return / annualized_volatility`, a Sharpe-style ratio at a 0% risk-free rate (the data has no risk-free series) |
| `max_drawdown` | decimal | Worst peak-to-trough fall of the index within the period (≤ 0); the period's starting level counts as a peak |

### `ticker_risk_return.csv`

Same metrics as `sector_summary.csv`, per stock. Use the `Full period` rows for the risk-return scatter (`annualized_volatility` on X, `annualized_return` on Y).

| Column | Type | Meaning |
|---|---|---|
| `ticker` | text | Stock ticker |
| `sector` | text | Sector of the ticker |
| `period_type` … `max_drawdown` | | Same definitions as in `sector_summary.csv` above |

### `correlation.csv`

Pearson correlation of daily returns over the full period, in long format: all 21 × 21 ordered pairs, so both (A, B) and (B, A) are present, and the diagonal (A, A) is exactly 1. This shape drops straight into a matrix visual with `ticker_a` on rows, `ticker_b` on columns and `correlation` as values.

| Column | Type | Meaning |
|---|---|---|
| `ticker_a` | text | First ticker |
| `sector_a` | text | Sector of `ticker_a` |
| `ticker_b` | text | Second ticker |
| `sector_b` | text | Sector of `ticker_b` |
| `correlation` | decimal | Correlation of the two tickers' daily returns (-1 to 1; in this data all pairs are positive) |
| `n_obs` | integer | Number of paired daily returns used (1,256) |

### `ticker_rolling_volatility.csv`

30-trading-day rolling volatility per stock. Rows only exist once a full 30-return window is available, so the series starts on **2020-02-14**.

| Column | Type | Meaning |
|---|---|---|
| `trade_date` | date | Last date of the 30-day window |
| `ticker` | text | Stock ticker |
| `sector` | text | Sector of the ticker |
| `rolling_vol_30d` | decimal | Sample standard deviation of the last 30 daily returns (daily scale) |
| `rolling_vol_30d_annualized` | decimal | `rolling_vol_30d × √252` |

### `sector_rolling_volatility.csv`

30-trading-day rolling volatility of each sector's equal-weighted daily return series. Starts on 2020-02-14.

| Column | Type | Meaning |
|---|---|---|
| `trade_date` | date | Last date of the 30-day window |
| `sector` | text | Sector |
| `rolling_vol_30d` | decimal | Sample standard deviation of the sector's last 30 daily returns (daily scale) |
| `rolling_vol_30d_annualized` | decimal | `rolling_vol_30d × √252` |

## Joining the tables in Power BI

There are no separate dimension files. The shared keys are:

- `ticker` links `ticker_daily`, `ticker_risk_return`, `ticker_rolling_volatility`, and `correlation` (as `ticker_a` or `ticker_b`).
- `sector` links every file (as `sector_a` / `sector_b` in `correlation`).
- `trade_date` links the four daily tables.

Because these are many-to-many between fact tables, you will likely want small ticker, sector and date dimension tables built inside Power BI (e.g. from distinct values), which is part of the separate Power BI build.

The DuckDB database also contains a sector-level correlation view (`sector_correlation`) that is not exported here.
