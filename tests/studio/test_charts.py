import pandas as pd
import plotly.graph_objects as go

from pycreditools.studio import charts
from pycreditools.studio.analyses import ks_table
from pycreditools.studio.data import population_filter


def test_bars_returns_figure_sorted_descending_with_highlight():
    series = pd.Series({"score_2": 0.10, "score_5": 0.30, "legacy_score": 0.05})
    fig = charts.bars(series, percent=True, highlight="legacy_score")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    bar = fig.data[0]
    assert list(bar.y) == ["legacy_score", "score_2", "score_5"]
    legacy_idx = list(bar.y).index("legacy_score")
    assert bar.marker.color[legacy_idx] == charts.TEXT_DIM
    other_idx = list(bar.y).index("score_5")
    assert bar.marker.color[other_idx] == charts.ACCENT


def test_bars_empty_series_returns_empty_figure():
    fig = charts.bars(pd.Series(dtype=float))
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_ks_curve_has_two_line_traces_and_marks_ks_point(sample_df, roles):
    hired = population_filter(sample_df, roles, "Contratados")
    table = ks_table(hired, "score_5", roles.actual_default_col, bins=10)
    fig = charts.ks_curve(table)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
    assert fig.data[0].y[-1] == 1.0  # cumulative goods reach 100%
    assert fig.data[1].y[-1] == 1.0  # cumulative bads reach 100%
    assert len(fig.layout.shapes) == 1  # the KS vline
    assert len(fig.layout.annotations) == 1


def test_ks_curve_empty_table_returns_empty_figure():
    fig = charts.ks_curve(pd.DataFrame())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0
