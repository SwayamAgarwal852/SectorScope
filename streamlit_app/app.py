"""SectorScope portfolio comparison tool.

Historical, descriptive analysis of 21 S&P 500 stocks (2020-2024 daily
closes). All figures come from the DuckDB analytics layer built from sql/.

Run locally:
    streamlit run streamlit_app/app.py
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import portfolio  # noqa: E402

st.set_page_config(page_title="SectorScope", layout="wide")

DEFAULT_HOLDINGS = ["AAPL", "MSFT", "JPM", "JNJ", "XOM"]
REBALANCE_LABELS = {"buy_and_hold": "Buy and hold", "daily": "Daily rebalance"}
BENCHMARK_NAME = "All 21 stocks, equal weight"

# Chart colors per theme. Categorical slots follow a palette validated for
# colorblind separation; grays carry context, never identity.
THEMES = {
    "light": {
        "portfolio": "#2a78d6",
        "holdings": "#eb6834",
        "benchmark": "#52514e",
        "context": "#c3c2b7",
        "surface": "#fcfcfb",
        "diverging": [[0.0, "#2a78d6"], [0.5, "#f0efec"], [1.0, "#e34948"]],
    },
    "dark": {
        "portfolio": "#3987e5",
        "holdings": "#d95926",
        "benchmark": "#c3c2b7",
        "context": "#5f5e5a",
        "surface": "#1a1a19",
        "diverging": [[0.0, "#3987e5"], [0.5, "#383835"], [1.0, "#e66767"]],
    },
}


@st.cache_resource
def get_connection():
    return portfolio.connect()


def cursor():
    # One cursor per call: DuckDB connections should not be shared across
    # Streamlit's script threads, cursors can be.
    return get_connection().cursor()


@st.cache_data(show_spinner=False)
def load_tickers() -> pd.DataFrame:
    return portfolio.tickers(cursor())


@st.cache_data(show_spinner=False)
def load_ticker_stats() -> pd.DataFrame:
    return portfolio.ticker_full_period(cursor())


@st.cache_data(show_spinner=False)
def load_series(tickers: tuple, weights: tuple, rebalance: str) -> pd.DataFrame:
    return portfolio.portfolio_series(cursor(), list(tickers), list(weights), rebalance)


@st.cache_data(show_spinner=False)
def load_metrics(tickers: tuple, weights: tuple, rebalance: str) -> dict:
    return portfolio.portfolio_metrics(cursor(), list(tickers), list(weights), rebalance)


@st.cache_data(show_spinner=False)
def load_correlation(tickers: tuple) -> pd.DataFrame:
    return portfolio.correlation_matrix(cursor(), list(tickers))


def pct(x: float, signed: bool = False) -> str:
    return f"{x:+.1%}" if signed else f"{x:.1%}"


def pp_delta(x: float) -> str:
    return f"{x * 100:+.1f} pp"


def base_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        hoverlabel=dict(font_size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


# ---------------------------------------------------------------- inputs

ticker_df = load_tickers()
sector_of = dict(zip(ticker_df["ticker"], ticker_df["sector"]))
all_tickers = list(ticker_df["ticker"])

with st.sidebar:
    st.header("Portfolio")
    holdings = st.multiselect(
        "Holdings",
        options=all_tickers,
        default=DEFAULT_HOLDINGS,
        format_func=lambda t: f"{t} · {sector_of[t]}",
    )
    weighting = st.segmented_control(
        "Weighting", ["Equal", "Custom"], default="Equal", required=True
    )

    raw_weights = {}
    if holdings and weighting == "Custom":
        st.caption("Enter any positive numbers; they are rescaled to sum to 100%.")
        default_w = round(100 / len(holdings), 1)
        for t in holdings:
            raw_weights[t] = st.number_input(
                f"{t} weight (%)", min_value=0.0, max_value=100.0, value=default_w, step=5.0, key=f"w_{t}"
            )
    else:
        raw_weights = {t: 1.0 for t in holdings}

    rebalance = st.segmented_control(
        "Rebalancing",
        list(REBALANCE_LABELS),
        format_func=REBALANCE_LABELS.get,
        default="buy_and_hold",
        required=True,
        help=(
            "Buy and hold: weights are set on 2020-01-02 and then drift with prices. "
            "Daily rebalance: weights are reset to target every day "
            "(the convention used for the equal-weighted sector figures)."
        ),
    )
    st.caption(f"Benchmark: {BENCHMARK_NAME}, same rebalancing.")

st.title("SectorScope · Portfolio comparison")
st.caption(
    "Historical, descriptive analysis of daily closing prices from 2020-01-02 to 2024-12-30. "
    "Returns are price returns (dividends excluded). Nothing here is a forecast or investment advice."
)

if not holdings:
    st.info("Select at least one holding in the sidebar.")
    st.stop()

total_raw = sum(raw_weights.values())
if total_raw <= 0:
    st.warning("Give at least one holding a weight above zero.")
    st.stop()

weights = {t: w / total_raw for t, w in raw_weights.items() if w > 0}
w_tickers, w_values = tuple(weights), tuple(weights.values())
bench_tickers, bench_values = tuple(all_tickers), tuple([1 / len(all_tickers)] * len(all_tickers))

theme = "dark" if st.context.theme.type == "dark" else "light"
colors = THEMES[theme]

series = load_series(w_tickers, w_values, rebalance)
bench_series = load_series(bench_tickers, bench_values, rebalance)
metrics = load_metrics(w_tickers, w_values, rebalance)
bench_metrics = load_metrics(bench_tickers, bench_values, rebalance)
ticker_stats = load_ticker_stats()

# ---------------------------------------------------------------- KPIs

kpis = st.columns(5)
kpis[0].metric(
    "Total return", pct(metrics["total_return"]),
    delta=pp_delta(metrics["total_return"] - bench_metrics["total_return"]),
    delta_description="vs benchmark",
)
kpis[1].metric(
    "Annualized return", pct(metrics["annualized_return"]),
    delta=pp_delta(metrics["annualized_return"] - bench_metrics["annualized_return"]),
    delta_description="vs benchmark",
)
kpis[2].metric(
    "Annualized volatility", pct(metrics["annualized_volatility"]),
    delta=pp_delta(metrics["annualized_volatility"] - bench_metrics["annualized_volatility"]),
    delta_color="inverse",
    delta_description="vs benchmark",
)
kpis[3].metric(
    "Return / risk", f"{metrics['return_to_risk']:.2f}",
    delta=f"{metrics['return_to_risk'] - bench_metrics['return_to_risk']:+.2f}",
    delta_description="vs benchmark",
    help="Annualized return ÷ annualized volatility (Sharpe-style, 0% risk-free rate).",
)
kpis[4].metric(
    "Max drawdown", pct(metrics["max_drawdown"]),
    delta=pp_delta(metrics["max_drawdown"] - bench_metrics["max_drawdown"]),
    delta_description="vs benchmark",
    help="Worst peak-to-trough fall in portfolio value over the period.",
)

# ---------------------------------------------------------------- cumulative return

st.subheader("Cumulative return")
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=bench_series["trade_date"], y=bench_series["cumulative_return"], name=BENCHMARK_NAME,
    mode="lines", line=dict(color=colors["benchmark"], width=1.5),
    hovertemplate="%{y:.1%}<extra>Benchmark</extra>",
))
fig.add_trace(go.Scatter(
    x=series["trade_date"], y=series["cumulative_return"], name="Your portfolio",
    mode="lines", line=dict(color=colors["portfolio"], width=2.5),
    hovertemplate="%{y:.1%}<extra>Portfolio</extra>",
))
fig.update_yaxes(tickformat=".0%", title=None, zeroline=True)
fig.update_xaxes(title=None)
fig.update_layout(hovermode="x unified")
st.plotly_chart(base_layout(fig, 380), key="cumulative")

with st.expander("Cumulative return data"):
    table = series[["trade_date", "cumulative_return"]].rename(columns={"cumulative_return": "portfolio"})
    table["benchmark"] = bench_series["cumulative_return"].to_numpy()
    st.dataframe(
        table, hide_index=True,
        column_config={
            "trade_date": st.column_config.DateColumn("Date"),
            "portfolio": st.column_config.NumberColumn("Portfolio", format="percent"),
            "benchmark": st.column_config.NumberColumn("Benchmark", format="percent"),
        },
    )

# ---------------------------------------------------------------- risk-return + sectors

left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("Risk vs. return")
    st.caption("Full period, annualized. Up and to the left is better.")
    is_holding = ticker_stats["ticker"].isin(weights)
    others, held = ticker_stats[~is_holding], ticker_stats[is_holding]
    hover = (
        "<b>%{text}</b> · %{customdata}<br>Return %{y:.1%}<br>Volatility %{x:.1%}<extra></extra>"
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=others["annualized_volatility"], y=others["annualized_return"], text=others["ticker"],
        customdata=others["sector"], name="Other stocks", mode="markers",
        marker=dict(size=9, color=colors["context"], line=dict(width=2, color=colors["surface"])),
        hovertemplate=hover,
    ))
    fig.add_trace(go.Scatter(
        x=held["annualized_volatility"], y=held["annualized_return"], text=held["ticker"],
        customdata=held["sector"], name="Holdings", mode="markers+text", textposition="top center",
        marker=dict(size=10, color=colors["holdings"], line=dict(width=2, color=colors["surface"])),
        hovertemplate=hover,
    ))
    for name, m, color, symbol in [
        ("Benchmark", bench_metrics, colors["benchmark"], "diamond"),
        ("Portfolio", metrics, colors["portfolio"], "star"),
    ]:
        fig.add_trace(go.Scatter(
            x=[m["annualized_volatility"]], y=[m["annualized_return"]], text=[name], name=name,
            mode="markers+text", textposition="bottom center",
            marker=dict(size=16, color=color, symbol=symbol, line=dict(width=2, color=colors["surface"])),
            hovertemplate=f"<b>{name}</b><br>Return %{{y:.1%}}<br>Volatility %{{x:.1%}}<extra></extra>",
        ))
    fig.update_xaxes(tickformat=".0%", title="Annualized volatility")
    fig.update_yaxes(tickformat=".0%", title="Annualized return")
    fig.update_layout(hovermode="closest")
    st.plotly_chart(base_layout(fig, 440), key="risk_return")

with right:
    st.subheader("Sector breakdown")
    st.caption(
        "Starting weights (they drift with prices under buy and hold)."
        if rebalance == "buy_and_hold" else "Target weights, reset daily."
    )
    by_sector = (
        pd.DataFrame({"ticker": list(weights), "weight": list(weights.values())})
        .assign(sector=lambda d: d["ticker"].map(sector_of))
        .groupby("sector", as_index=False)
        .agg(weight=("weight", "sum"), tickers=("ticker", ", ".join))
        .sort_values("weight")
    )
    fig = go.Figure(go.Bar(
        x=by_sector["weight"], y=by_sector["sector"], orientation="h",
        marker=dict(color=colors["portfolio"], cornerradius=4),
        text=[pct(w) for w in by_sector["weight"]], textposition="outside", cliponaxis=False,
        customdata=by_sector["tickers"],
        hovertemplate="<b>%{y}</b><br>Weight %{x:.1%}<br>%{customdata}<extra></extra>",
    ))
    fig.update_xaxes(tickformat=".0%", title=None, range=[0, min(1.0, by_sector["weight"].max() * 1.25)])
    fig.update_yaxes(title=None)
    fig.update_layout(showlegend=False, bargap=0.35)
    st.plotly_chart(base_layout(fig, 60 + 46 * len(by_sector)), key="sectors")

# ---------------------------------------------------------------- holdings table

with st.expander("Holdings detail", expanded=False):
    detail = (
        ticker_stats[ticker_stats["ticker"].isin(weights)]
        .assign(weight=lambda d: d["ticker"].map(weights))
        .sort_values("weight", ascending=False)
        [["ticker", "sector", "weight", "total_return", "annualized_return",
          "annualized_volatility", "return_to_risk", "max_drawdown"]]
    )
    st.dataframe(
        detail, hide_index=True,
        column_config={
            "ticker": "Ticker", "sector": "Sector",
            "weight": st.column_config.NumberColumn("Weight", format="percent"),
            "total_return": st.column_config.NumberColumn("Total return", format="percent"),
            "annualized_return": st.column_config.NumberColumn("Ann. return", format="percent"),
            "annualized_volatility": st.column_config.NumberColumn("Ann. volatility", format="percent"),
            "return_to_risk": st.column_config.NumberColumn("Return / risk", format="%.2f"),
            "max_drawdown": st.column_config.NumberColumn("Max drawdown", format="percent"),
        },
    )

# ---------------------------------------------------------------- correlation

st.subheader("Correlation of daily returns")
if len(weights) < 2:
    st.info("Add a second holding to see how your holdings move together.")
else:
    corr = load_correlation(w_tickers)
    n = len(corr)
    off_diag = corr.where(~pd.DataFrame(
        [[i == j for j in range(n)] for i in range(n)], index=corr.index, columns=corr.columns
    )).stack()
    st.caption(
        f"Average pairwise correlation: **{off_diag.mean():.2f}** "
        f"(lowest {off_diag.min():.2f}, highest {off_diag.max():.2f}). "
        "Lower values mean the holdings tended to move less in step, which is the basis of diversification."
    )
    fig = go.Figure(go.Heatmap(
        z=corr.to_numpy(), x=list(corr.columns), y=list(corr.index),
        zmin=-1, zmax=1, colorscale=colors["diverging"], xgap=2, ygap=2,
        text=corr.to_numpy(), texttemplate="%{text:.2f}" if n <= 12 else None,
        colorbar=dict(title="ρ", thickness=12, tickvals=[-1, -0.5, 0, 0.5, 1]),
        hovertemplate="%{y} vs %{x}<br>Correlation %{z:.2f}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(side="top", title=None)
    side = min(640, 120 + 48 * n)
    st.plotly_chart(base_layout(fig, side), key="correlation")
    with st.expander("Correlation data"):
        st.dataframe(corr.round(3))
