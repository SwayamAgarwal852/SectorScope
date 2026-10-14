-- 03_sector_aggregates.sql
-- Equal-weighted sector performance: each day's sector return is the simple
-- average of its constituents' daily returns (equal weights, rebalanced daily).
-- The data has no market-cap figures, so cap-weighting is not possible.

CREATE OR REPLACE VIEW sector_daily_returns AS
SELECT
    trade_date,
    sector,
    AVG(daily_return) AS daily_return,
    COUNT(*)          AS n_constituents
FROM ticker_daily_returns
WHERE daily_return IS NOT NULL
GROUP BY trade_date, sector;

-- Compounded growth of the equal-weighted sector index since the first close.
CREATE OR REPLACE VIEW sector_cumulative_returns AS
SELECT
    trade_date,
    sector,
    daily_return,
    n_constituents,
    exp(SUM(ln(1 + daily_return)) OVER (PARTITION BY sector ORDER BY trade_date)) - 1 AS cumulative_return
FROM sector_daily_returns;

-- 30-trading-day rolling volatility of each sector's daily return series.
CREATE OR REPLACE VIEW sector_rolling_volatility AS
SELECT
    trade_date,
    sector,
    rolling_vol_30d,
    rolling_vol_30d * sqrt(252) AS rolling_vol_30d_annualized
FROM (
    SELECT
        trade_date, sector,
        STDDEV_SAMP(daily_return) OVER w AS rolling_vol_30d,
        COUNT(daily_return)       OVER w AS n_obs
    FROM sector_daily_returns
    WINDOW w AS (PARTITION BY sector ORDER BY trade_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
)
WHERE n_obs = 30;

-- Calendar-year sector performance (return compounded within each year).
CREATE OR REPLACE VIEW sector_yearly_returns AS
SELECT
    sector,
    year(trade_date)                       AS year,
    exp(SUM(ln(1 + daily_return))) - 1     AS annual_return,
    STDDEV_SAMP(daily_return) * sqrt(252)  AS annualized_volatility,
    COUNT(*)                               AS n_trading_days
FROM sector_daily_returns
GROUP BY sector, year(trade_date);
