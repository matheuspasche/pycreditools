"""Themed Plotly figure builders (pure, no streamlit).

Registers the `pct_dark` template on import. Pages render the returned
`go.Figure` objects with `st.plotly_chart` — that is the only `st.*` touchpoint.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

BG = "#0B0E14"
SURFACE = "#141925"
BORDER = "#232A3B"
TEXT = "#E6EAF2"
TEXT_DIM = "#94A0B8"
ACCENT = "#4F8CFF"
SUCCESS = "#3DD68C"
WARNING = "#F5A623"
DANGER = "#FF5C5C"

COLORWAY = ["#4F8CFF", "#3DD68C", "#F5C84B", "#F5853F", "#FF5C5C", "#9B8CFF"]

RISK_COLORS = {
    "A": "#3DD68C",
    "B": "#9BD460",
    "C": "#F5C84B",
    "D": "#F5853F",
    "E": "#FF5C5C",
}

_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, system-ui, sans-serif", "color": TEXT},
        colorway=COLORWAY,
        xaxis={"gridcolor": BORDER, "zerolinecolor": BORDER, "linecolor": BORDER},
        yaxis={"gridcolor": BORDER, "zerolinecolor": BORDER, "linecolor": BORDER},
        legend={"bgcolor": "rgba(0,0,0,0)"},
        hoverlabel={"bgcolor": SURFACE, "font": {"color": TEXT}},
    )
)

pio.templates["pct_dark"] = _TEMPLATE


def _apply_layout(fig: go.Figure, title: str = "", height: int = 380) -> go.Figure:
    """Apply the shared dark layout (template, title, height, tight margins)."""
    fig.update_layout(
        template="pct_dark",
        title=title or None,
        height=height,
        margin={"l": 40, "r": 20, "t": 40 if title else 20, "b": 40},
    )
    return fig


def frontier(df: pd.DataFrame, *, x: str = "approval_rate", y: str = "bad_rate") -> go.Figure:
    """Efficient frontier: approval rate vs bad rate."""
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Scatter(x=df[x], y=df[y], mode="lines+markers"))
    return _apply_layout(fig, "Fronteira eficiente")


def funnel(df: pd.DataFrame, *, stage_col: str = "stage", count_col: str = "n") -> go.Figure:
    """Policy funnel (volume per stage)."""
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Funnel(y=df[stage_col], x=df[count_col]))
    return _apply_layout(fig, "Funil da política")


def ks_curve(
    df: pd.DataFrame, *, x: str = "decile", y_good: str = "cum_good", y_bad: str = "cum_bad"
) -> go.Figure:
    """Cumulative good/bad curves for KS visualization."""
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Scatter(x=df[x], y=df[y_good], mode="lines", name="Bons (cum.)"))
        fig.add_trace(go.Scatter(x=df[x], y=df[y_bad], mode="lines", name="Maus (cum.)"))
    return _apply_layout(fig, "Curva KS")


def bars(df: pd.DataFrame, *, x: str, y: str) -> go.Figure:
    """Generic themed bar chart."""
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Bar(x=df[x], y=df[y]))
    return _apply_layout(fig, "")


def vintage_stability(
    df: pd.DataFrame,
    *,
    time_col: str = "safra",
    rating_col: str = "rating",
    rate_col: str = "bad_rate",
) -> go.Figure:
    """Bad rate per rating tier across vintages."""
    fig = go.Figure()
    if not df.empty:
        for rating, sub in df.groupby(rating_col):
            fig.add_trace(
                go.Scatter(
                    x=sub[time_col],
                    y=sub[rate_col],
                    mode="lines+markers",
                    name=str(rating),
                    line={"color": RISK_COLORS.get(str(rating))},
                )
            )
    return _apply_layout(fig, "Estabilidade por safra")


def crash(
    df: pd.DataFrame,
    *,
    x: str = "stress_factor",
    y: str = "bad_rate",
    breakeven: float | None = None,
) -> go.Figure:
    """Crash-test curve with an optional breakeven marker."""
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Scatter(x=df[x], y=df[y], mode="lines+markers"))
        if breakeven is not None:
            fig.add_vline(x=breakeven, line={"color": DANGER, "dash": "dash"})
    return _apply_layout(fig, "Crash test")


def pareto(df: pd.DataFrame, *, x: str, y: str) -> go.Figure:
    """Pareto frontier scatter."""
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Scatter(x=df[x], y=df[y], mode="markers"))
    return _apply_layout(fig, "Fronteira de Pareto")


def distribution(df: pd.DataFrame, *, col: str, nbins: int = 30) -> go.Figure:
    """Histogram of a score/feature distribution."""
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Histogram(x=df[col], nbinsx=nbins))
    return _apply_layout(fig, "Distribuição")
