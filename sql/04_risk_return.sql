-- 04_risk_return.sql
-- Risk-return summary per ticker and per sector, for the full period and for
-- each calendar year. One row per (entity, period); period is 'Full period'
-- or a year such as '2022'.
--
-- Every metric is computed from the daily returns that fall inside the
-- period, so a period's return is measured from the last close before it
-- (for 2020 / Full period that base is the first close, 2020-01-02).
--   total_return           compounded return over the period
--   annualized_return      (1 + total_return) ^ (252 / n_return_days) - 1  (CAGR)
--   annualized_volatility  sample std dev of daily returns * sqrt(252)
--   return_to_risk         annualized_return / annualized_volatility
--                          (Sharpe-style ratio at a 0% risk-free rate; the data
--                          has no risk-free series)
--   max_drawdown           worst peak-to-trough decline within the period,
--                          with the starting level (1.0) counted as a peak

-- Ticker and sector daily returns stacked into one series so the period
-- metrics below are defined once for both.
CREATE OR REPLACE VIEW entity_daily_returns AS
SELECT 'ticker' AS entity_type, ticker AS entity, sector, trade_date, daily_return
FROM ticker_daily_returns
WHERE daily_return IS NOT NULL
UNION ALL
SELECT 'sector', sector, sector, trade_date, daily_return
FROM sector_daily_returns;

CREATE OR REPLACE VIEW entity_period_risk_return AS
WITH by_period AS (
    SELECT *, 'full' AS period_type, 'Full period' AS period FROM entity_daily_returns
    UNION ALL
    SELECT *, 'year', CAST(year(trade_date) AS VARCHAR) FROM entity_daily_returns
),
growth AS (
    SELECT *,
           exp(SUM(ln(1 + daily_return)) OVER w) AS growth
    FROM by_period
    WINDOW w AS (PARTITION BY entity_type, entity, period ORDER BY trade_date)
),
drawdown AS (
    SELECT *,
           growth / GREATEST(1, MAX(growth) OVER (PARTITION BY entity_type, entity, period ORDER BY trade_date)) - 1
               AS drawdown
    FROM growth
),
stats AS (
    SELECT
        entity_type,
        entity,
        ANY_VALUE(sector)                      AS sector,
        period_type,
        period,
        MIN(trade_date)                        AS period_start,
        MAX(trade_date)                        AS period_end,
        COUNT(*)                               AS n_return_days,
        ARG_MAX(growth, trade_date) - 1        AS total_return,
        STDDEV_SAMP(daily_return) * sqrt(252)  AS annualized_volatility,
        MIN(drawdown)                          AS max_drawdown
    FROM drawdown
    GROUP BY entity_type, entity, period_type, period
)
SELECT
    entity_type,
    entity,
    sector,
    period_type,
    period,
    period_start,
    period_end,
    n_return_days,
    total_return,
    pow(1 + total_return, 252.0 / n_return_days) - 1 AS annualized_return,
    annualized_volatility,
    (pow(1 + total_return, 252.0 / n_return_days) - 1) / annualized_volatility AS return_to_risk,
    max_drawdown
FROM stats;

CREATE OR REPLACE VIEW ticker_risk_return AS
SELECT
    entity AS ticker, sector, period_type, period, period_start, period_end, n_return_days,
    total_return, annualized_return, annualized_volatility, return_to_risk, max_drawdown
FROM entity_period_risk_return
WHERE entity_type = 'ticker';

CREATE OR REPLACE VIEW sector_risk_return AS
WITH constituents AS (
    SELECT sector, COUNT(*) AS n_constituents, string_agg(ticker, ', ' ORDER BY ticker) AS tickers
    FROM sector_map
    GROUP BY sector
)
SELECT
    r.sector, c.n_constituents, c.tickers, r.period_type, r.period, r.period_start, r.period_end,
    r.n_return_days, r.total_return, r.annualized_return, r.annualized_volatility,
    r.return_to_risk, r.max_drawdown
FROM entity_period_risk_return r
JOIN constituents c USING (sector)
WHERE r.entity_type = 'sector';
