-- 04_risk_return.sql
-- Full-period risk-return summary per ticker and per sector.
--   total_return           growth from the first close to the last close
--   annualized_return      CAGR: (1 + total_return) ^ (252 / n_return_days) - 1
--   annualized_volatility  sample std dev of daily returns * sqrt(252)
--   return_to_risk         annualized_return / annualized_volatility
--                          (Sharpe-style ratio at a 0% risk-free rate; the data
--                          has no risk-free series)
--   max_drawdown           worst peak-to-trough decline of the cumulative index

CREATE OR REPLACE VIEW ticker_risk_return AS
WITH idx AS (
    SELECT ticker, sector, trade_date, daily_return, 1 + cumulative_return AS growth
    FROM ticker_daily_returns
),
drawdowns AS (
    SELECT ticker, MIN(drawdown) AS max_drawdown
    FROM (
        SELECT ticker, growth / MAX(growth) OVER (PARTITION BY ticker ORDER BY trade_date) - 1 AS drawdown
        FROM idx
    )
    GROUP BY ticker
),
stats AS (
    SELECT
        ticker,
        ANY_VALUE(sector)                      AS sector,
        MIN(trade_date)                        AS start_date,
        MAX(trade_date)                        AS end_date,
        COUNT(daily_return)                    AS n_return_days,
        ARG_MAX(growth, trade_date) - 1        AS total_return,
        STDDEV_SAMP(daily_return) * sqrt(252)  AS annualized_volatility
    FROM idx
    GROUP BY ticker
)
SELECT
    s.ticker,
    s.sector,
    s.start_date,
    s.end_date,
    s.n_return_days,
    s.total_return,
    pow(1 + s.total_return, 252.0 / s.n_return_days) - 1 AS annualized_return,
    s.annualized_volatility,
    (pow(1 + s.total_return, 252.0 / s.n_return_days) - 1) / s.annualized_volatility AS return_to_risk,
    d.max_drawdown
FROM stats s
JOIN drawdowns d USING (ticker);

CREATE OR REPLACE VIEW sector_risk_return AS
WITH idx AS (
    SELECT sector, trade_date, daily_return, 1 + cumulative_return AS growth
    FROM sector_cumulative_returns
),
drawdowns AS (
    -- The sector series starts at the first return date, so the starting
    -- index level (1.0) is included in the running peak explicitly.
    SELECT sector, MIN(drawdown) AS max_drawdown
    FROM (
        SELECT sector,
               growth / GREATEST(1, MAX(growth) OVER (PARTITION BY sector ORDER BY trade_date)) - 1 AS drawdown
        FROM idx
    )
    GROUP BY sector
),
constituents AS (
    SELECT sector, COUNT(*) AS n_constituents, string_agg(ticker, ', ' ORDER BY ticker) AS tickers
    FROM sector_map
    GROUP BY sector
),
stats AS (
    SELECT
        sector,
        MIN(trade_date)                        AS start_date,
        MAX(trade_date)                        AS end_date,
        COUNT(daily_return)                    AS n_return_days,
        ARG_MAX(growth, trade_date) - 1        AS total_return,
        STDDEV_SAMP(daily_return) * sqrt(252)  AS annualized_volatility
    FROM idx
    GROUP BY sector
)
SELECT
    s.sector,
    c.n_constituents,
    c.tickers,
    s.start_date,
    s.end_date,
    s.n_return_days,
    s.total_return,
    pow(1 + s.total_return, 252.0 / s.n_return_days) - 1 AS annualized_return,
    s.annualized_volatility,
    (pow(1 + s.total_return, 252.0 / s.n_return_days) - 1) / s.annualized_volatility AS return_to_risk,
    d.max_drawdown
FROM stats s
JOIN drawdowns d USING (sector)
JOIN constituents c USING (sector);
