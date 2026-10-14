-- 05_correlation.sql
-- Pearson correlation of daily returns over the full period, in long format
-- (one row per ordered pair, diagonal included) so it can feed a matrix
-- visual or heatmap directly.

CREATE OR REPLACE VIEW ticker_correlation AS
SELECT
    a.ticker AS ticker_a,
    a.sector AS sector_a,
    b.ticker AS ticker_b,
    b.sector AS sector_b,
    -- Self-correlation is set to exactly 1 (CORR can return 1.0000000000000002).
    CASE WHEN a.ticker = b.ticker THEN 1.0 ELSE CORR(a.daily_return, b.daily_return) END AS correlation,
    COUNT(*)                             AS n_obs
FROM ticker_daily_returns a
JOIN ticker_daily_returns b USING (trade_date)
WHERE a.daily_return IS NOT NULL
  AND b.daily_return IS NOT NULL
GROUP BY a.ticker, a.sector, b.ticker, b.sector;

CREATE OR REPLACE VIEW sector_correlation AS
SELECT
    a.sector AS sector_a,
    b.sector AS sector_b,
    -- Self-correlation is set to exactly 1 (CORR can return 1.0000000000000002).
    CASE WHEN a.sector = b.sector THEN 1.0 ELSE CORR(a.daily_return, b.daily_return) END AS correlation,
    COUNT(*)                             AS n_obs
FROM sector_daily_returns a
JOIN sector_daily_returns b USING (trade_date)
GROUP BY a.sector, b.sector;
