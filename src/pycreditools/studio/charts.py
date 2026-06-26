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


def frontier(
    df: pd.DataFrame,
    *,
    x: str = "approval_rate",
    y: str = "default_rate",
    hue_col: str | None = None,
    legacy: tuple[float, float] | None = None,
    scenarios: dict[str, tuple[float, float]] | None = None,
) -> go.Figure:
    """Efficient frontier: approval rate vs default rate, one line per `hue_col` group.

    `legacy` is an optional `(approval_rate, bad_rate)` reference point; `scenarios`
    is an optional `{label: (approval_rate, default_rate)}` mapping highlighted on top.
    """
    fig = go.Figure()
    if not df.empty:
        if hue_col and hue_col in df.columns:
            for name, group in df.groupby(hue_col):
                ordered = group.sort_values(x)
                fig.add_trace(
                    go.Scatter(
                        x=ordered[x], y=ordered[y], mode="lines+markers", name=str(name)
                    )
                )
        else:
            ordered = df.sort_values(x)
            fig.add_trace(go.Scatter(x=ordered[x], y=ordered[y], mode="lines+markers"))
    if legacy is not None:
        fig.add_trace(
            go.Scatter(
                x=[legacy[0]],
                y=[legacy[1]],
                mode="markers",
                name="Legado",
                marker={"symbol": "x", "size": 14, "color": DANGER},
            )
        )
    if scenarios:
        for label, (sx, sy) in scenarios.items():
            fig.add_trace(
                go.Scatter(
                    x=[sx],
                    y=[sy],
                    mode="markers+text",
                    name=label,
                    text=[label],
                    textposition="top center",
                    marker={"size": 12, "symbol": "star"},
                )
            )
    return _apply_layout(fig, "Fronteira eficiente")


def funnel(df: pd.DataFrame, *, stage_col: str = "stage", count_col: str = "n") -> go.Figure:
    """Policy funnel (volume per stage)."""
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Funnel(y=df[stage_col], x=df[count_col]))
    return _apply_layout(fig, "Funil da política")


def bars(series: pd.Series, *, percent: bool = True, highlight: str | None = None) -> go.Figure:
    """Horizontal bar chart from a labeled `series`, sorted descending top-to-bottom.

    `highlight` (e.g. the legacy score's label) is rendered in a muted color.
    """
    fig = go.Figure()
    if not series.empty:
        ordered = series.sort_values(ascending=True)
        labels = [str(idx) for idx in ordered.index]
        colors = [TEXT_DIM if label == highlight else ACCENT for label in labels]
        text = [f"{v * 100:.1f}%" if percent else f"{v:.2f}" for v in ordered.values]
        fig.add_trace(
            go.Bar(
                x=ordered.values,
                y=labels,
                orientation="h",
                marker={"color": colors},
                text=text,
                textposition="outside",
            )
        )
    return _apply_layout(fig, "", height=max(220, 40 * len(series) + 80))


def ks_curve(table_df: pd.DataFrame) -> go.Figure:
    """Cumulative good/bad curves over `Bucket`, with the max-gap (KS) point marked."""
    fig = go.Figure()
    if not table_df.empty:
        df = table_df.sort_values("Bucket")
        fig.add_trace(
            go.Scatter(
                x=df["Bucket"],
                y=df["Cum_Goods"],
                mode="lines+markers",
                name="Bons (cum.)",
                line={"color": SUCCESS},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df["Bucket"],
                y=df["Cum_Bads"],
                mode="lines+markers",
                name="Maus (cum.)",
                line={"color": DANGER},
                fill="tonexty",
                fillcolor="rgba(79,140,255,0.15)",
            )
        )
        ks_row = df.loc[df["KS"].idxmax()]
        fig.add_vline(x=ks_row["Bucket"], line={"color": ACCENT, "dash": "dash"})
        fig.add_annotation(
            x=ks_row["Bucket"],
            y=(ks_row["Cum_Goods"] + ks_row["Cum_Bads"]) / 2,
            text=f"KS = {ks_row['KS'] * 100:.1f}%",
            showarrow=False,
            yshift=14,
            font={"color": TEXT},
        )
    return _apply_layout(fig, "Curva KS")


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


def rating_bars(
    table: pd.DataFrame,
    *,
    rating_col: str = "Rating",
    volume_col: str = "Vol_Esperado",
    rate_col: str = "Inad_Stressed",
) -> go.Figure:
    """Volume per rating tier (A..E), colored by `RISK_COLORS`, with bad rate as labels."""
    fig = go.Figure()
    if not table.empty:
        ordered = table.sort_values(rating_col)
        labels = [str(v) for v in ordered[rating_col]]
        colors = [RISK_COLORS.get(label, ACCENT) for label in labels]
        text = [f"{v * 100:.1f}%" if pd.notna(v) else "—" for v in ordered[rate_col]]
        fig.add_trace(
            go.Bar(
                x=labels,
                y=ordered[volume_col],
                marker={"color": colors},
                text=text,
                textposition="outside",
                name="Volume swap-in",
            )
        )
    return _apply_layout(fig, "Swap-in por rating")


def heatmap(table: pd.DataFrame, *, title: str = "") -> go.Figure:
    """Themed heatmap from a `rating x segment` crosstab (index/columns become axis labels)."""
    fig = go.Figure()
    if not table.empty:
        fig.add_trace(
            go.Heatmap(
                z=table.values,
                x=[str(c) for c in table.columns],
                y=[str(i) for i in table.index],
                colorscale=[[0, SURFACE], [1, ACCENT]],
                showscale=True,
            )
        )
    return _apply_layout(fig, title, height=max(260, 50 * len(table.index) + 100))


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
