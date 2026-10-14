"""Portfolio calculations used by the Streamlit app, checked against the SQL layer."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import portfolio
from conftest import EXPECTED_SECTORS, N_DATES, N_TICKERS

METRICS = ["total_return", "annualized_return", "annualized_volatility", "return_to_risk", "max_drawdown"]
APP = Path(__file__).resolve().parents[1] / "streamlit_app" / "app.py"


@pytest.fixture(scope="module")
def pcon(db_path):
    with portfolio.connect(db_path) as c:
        yield c


@pytest.fixture(scope="module")
def ticker_stats(pcon):
    return portfolio.ticker_full_period(pcon).set_index("ticker")


@pytest.mark.parametrize("rebalance", portfolio.REBALANCE_MODES)
def test_single_stock_portfolio_reproduces_ticker_metrics(pcon, ticker_stats, rebalance):
    assert len(ticker_stats) == N_TICKERS
    for ticker, expected in ticker_stats.iterrows():
        m = portfolio.portfolio_metrics(pcon, [ticker], [1.0], rebalance)
        for k in METRICS:
            assert m[k] == pytest.approx(expected[k], abs=1e-10), (ticker, rebalance, k)


@pytest.mark.parametrize("sector", sorted(EXPECTED_SECTORS))
def test_equal_weight_daily_rebalanced_portfolio_reproduces_sector(pcon, sector):
    members = sorted(EXPECTED_SECTORS[sector])
    m = portfolio.portfolio_metrics(pcon, members, [1 / len(members)] * len(members), "daily")
    expected = pcon.execute(
        f"SELECT {', '.join(METRICS)} FROM sector_risk_return WHERE sector = ? AND period = 'Full period'",
        [sector],
    ).df().iloc[0]
    for k in METRICS:
        assert m[k] == pytest.approx(expected[k], abs=1e-10), (sector, k)


def test_buy_and_hold_total_is_weighted_average_of_holdings(pcon, ticker_stats):
    tickers, weights = ["AAPL", "XOM", "JNJ"], [0.5, 0.3, 0.2]
    m = portfolio.portfolio_metrics(pcon, tickers, weights, "buy_and_hold")
    expected = sum(w * ticker_stats.loc[t, "total_return"] for t, w in zip(tickers, weights))
    assert m["total_return"] == pytest.approx(expected, abs=1e-10)


def test_rebalancing_modes_differ_for_multi_stock_portfolio(pcon):
    args = (["NVDA", "JNJ"], [0.5, 0.5])
    hold = portfolio.portfolio_metrics(pcon, *args, "buy_and_hold")
    daily = portfolio.portfolio_metrics(pcon, *args, "daily")
    assert hold["total_return"] != pytest.approx(daily["total_return"], abs=1e-3)


DRIFT_TICKERS, DRIFT_WEIGHTS = ["NVDA", "JNJ", "XOM", "JPM"], [0.25, 0.25, 0.25, 0.25]


def test_buy_and_hold_sector_weights_drift_with_uneven_growth(pcon, ticker_stats):
    w = portfolio.sector_weights(pcon, DRIFT_TICKERS, DRIFT_WEIGHTS, "buy_and_hold").set_index("sector")
    assert w["starting_weight"].sum() == pytest.approx(1)
    assert w["current_weight"].sum() == pytest.approx(1)
    assert w["starting_weight"].to_dict() == pytest.approx(
        {"Technology": 0.25, "Healthcare": 0.25, "Energy": 0.25, "Financials": 0.25}
    )
    # NVDA grew far more than the others, so Technology's share rises and the rest shrink.
    assert w.loc["Technology", "current_weight"] > 0.25
    for sector in ("Healthcare", "Energy", "Financials"):
        assert w.loc[sector, "current_weight"] < 0.25
    # Current weight = starting weight x growth, renormalized.
    growth = {t: 1 + ticker_stats.loc[t, "total_return"] for t in DRIFT_TICKERS}
    expected_tech = 0.25 * growth["NVDA"] / sum(0.25 * g for g in growth.values())
    assert w.loc["Technology", "current_weight"] == pytest.approx(expected_tech, abs=1e-10)


def test_daily_rebalanced_sector_weights_do_not_drift(pcon):
    w = portfolio.sector_weights(pcon, DRIFT_TICKERS, DRIFT_WEIGHTS, "daily")
    assert w["current_weight"].to_numpy() == pytest.approx(w["starting_weight"].to_numpy(), abs=1e-12)


@pytest.mark.parametrize("rebalance", portfolio.REBALANCE_MODES)
def test_series_shape(pcon, rebalance):
    s = portfolio.portfolio_series(pcon, ["AAPL", "MSFT"], [0.5, 0.5], rebalance)
    assert len(s) == N_DATES
    assert s["cumulative_return"].iloc[0] == 0
    assert s["daily_return"].isna().sum() == 1
    assert s["cumulative_return"].notna().all()


def test_correlation_matrix_is_square_symmetric_and_sector_ordered(pcon):
    m = portfolio.correlation_matrix(pcon, ["XOM", "AAPL", "JPM"])
    assert list(m.index) == list(m.columns) == ["XOM", "JPM", "AAPL"]  # Energy, Financials, Technology
    assert (m.to_numpy().diagonal() == 1).all()
    assert (m.to_numpy() == m.to_numpy().T).all()


@pytest.mark.parametrize(
    "tickers, weights, rebalance",
    [
        ([], [], "daily"),
        (["AAPL"], [0.5], "daily"),
        (["AAPL", "MSFT"], [1.2, -0.2], "daily"),
        (["AAPL", "AAPL"], [0.5, 0.5], "daily"),
        (["AAPL"], [1.0], "monthly"),
    ],
)
def test_invalid_inputs_are_rejected(pcon, tickers, weights, rebalance):
    with pytest.raises(ValueError):
        portfolio.portfolio_metrics(pcon, tickers, weights, rebalance)


# ---------------------------------------------------------------- app smoke test

def test_app_renders_default_portfolio():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    assert len(at.metric) == 5
    assert len(at.get("plotly_chart")) == 4


def test_app_handles_custom_weights_daily_rebalance_and_single_holding():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.sidebar.segmented_control[0].set_value("Custom").run()
    at.sidebar.number_input[0].set_value(50.0).run()
    at.sidebar.segmented_control[1].set_value("daily").run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 4

    at.sidebar.multiselect[0].set_value(["NVDA"]).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 3  # no correlation heatmap for one holding

    at.sidebar.multiselect[0].set_value([]).run()
    assert not at.exception
    assert any("Select at least one holding" in i.value for i in at.info)
