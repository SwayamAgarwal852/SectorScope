-- 02_returns.sql
-- Daily and cumulative price returns per ticker (close-to-close). Prices are
-- split-adjusted but not dividend-adjusted, so these are price returns.

-- daily_return / log_return are NULL on each ticker's first date (no prior close).
-- cumulative_return is measured from the ticker's first close, so it is 0 on day one.
CREATE OR REPLACE VIEW ticker_daily_returns AS
SELECT
    trade_date,
    ticker,
    sector,
    close,
    volume,
    close / LAG(close) OVER w - 1          AS daily_return,
    ln(close / LAG(close) OVER w)          AS log_return,
    close / FIRST_VALUE(close) OVER w - 1  AS cumulative_return
FROM prices
WINDOW w AS (PARTITION BY ticker ORDER BY trade_date);

-- 30-trading-day rolling volatility (sample std dev of daily returns).
-- Rows are emitted only once a full 30-return window exists.
CREATE OR REPLACE VIEW ticker_rolling_volatility AS
SELECT
    trade_date,
    ticker,
    sector,
    rolling_vol_30d,
    rolling_vol_30d * sqrt(252) AS rolling_vol_30d_annualized
FROM (
    SELECT
        trade_date, ticker, sector,
        STDDEV_SAMP(daily_return) OVER w AS rolling_vol_30d,
        COUNT(daily_return)       OVER w AS n_obs
    FROM ticker_daily_returns
    WINDOW w AS (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
)
WHERE n_obs = 30;
