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


def test_rating_bars_colors_by_risk_rating_and_orders_a_to_e():
    table = pd.DataFrame(
        {
            "Rating": ["C", "A", "B"],
            "Vol_Esperado": [100, 300, 200],
            "Inad_Stressed": [0.10, 0.02, 0.05],
        }
    )
    fig = charts.rating_bars(table)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    bar = fig.data[0]
    assert list(bar.x) == ["A", "B", "C"]
    assert list(bar.marker.color) == [
        charts.RISK_COLORS["A"],
        charts.RISK_COLORS["B"],
        charts.RISK_COLORS["C"],
    ]
    assert list(bar.text) == ["2.0%", "5.0%", "10.0%"]


def test_rating_bars_empty_table_returns_empty_figure():
    fig = charts.rating_bars(pd.DataFrame())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_heatmap_builds_a_heatmap_trace_from_a_crosstab():
    table = pd.DataFrame(
        {"Sudeste": [10, 20], "Sul": [5, 15]}, index=pd.Index(["A", "B"], name="Rating")
    )
    fig = charts.heatmap(table, title="Volume swap-in")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    heat = fig.data[0]
    assert list(heat.x) == ["Sudeste", "Sul"]
    assert list(heat.y) == ["A", "B"]
    assert heat.z.tolist() == [[10, 5], [20, 15]]


def test_heatmap_empty_table_returns_empty_figure():
    fig = charts.heatmap(pd.DataFrame())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_frontier_draws_one_line_per_hue_group():
    df = pd.DataFrame(
        {
            "Score_Model": ["score_4", "score_4", "score_5", "score_5"],
            "approval_rate": [0.3, 0.5, 0.2, 0.4],
            "default_rate": [0.08, 0.04, 0.06, 0.03],
        }
    )
    fig = charts.frontier(df, hue_col="Score_Model")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
    names = {trace.name for trace in fig.data}
    assert names == {"score_4", "score_5"}


def test_frontier_overlays_legacy_marker_and_scenario_points():
    df = pd.DataFrame({"approval_rate": [0.2, 0.4], "default_rate": [0.06, 0.03]})
    fig = charts.frontier(
        df,
        legacy=(0.3, 0.05),
        scenarios={"Conservador": (0.2, 0.06), "Agressivo": (0.4, 0.03)},
    )
    # 1 frontier line + 1 legacy marker + 2 scenario markers
    assert len(fig.data) == 4
    names = [trace.name for trace in fig.data]
    assert "Legado" in names
    assert "Conservador" in names
    assert "Agressivo" in names


def test_frontier_empty_df_returns_empty_figure():
    fig = charts.frontier(pd.DataFrame())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_pareto_draws_all_combinations_frontier_and_best_star():
    all_df = pd.DataFrame(
        {"overall_approval_rate": [0.2, 0.3, 0.5], "overall_default_rate": [0.02, 0.04, 0.08]}
    )
    pareto_df = all_df.iloc[[0, 2]]
    fig = charts.pareto(all_df, pareto_df, (0.5, 0.08))
    assert isinstance(fig, go.Figure)
    names = [trace.name for trace in fig.data]
    assert "Combinações" in names
    assert "Fronteira de Pareto" in names
    assert "Melhor combinação" in names
    best_trace = next(t for t in fig.data if t.name == "Melhor combinação")
    assert best_trace.marker.symbol == "star"


def test_pareto_with_constraints_draws_guides_and_shaded_region():
    all_df = pd.DataFrame({"overall_approval_rate": [0.3], "overall_default_rate": [0.04]})
    fig = charts.pareto(
        all_df, all_df, (0.3, 0.04), constraints=(0.05, 0.30)
    )
    assert len(fig.layout.shapes) == 3  # feasible-region rect + vline + hline
    rect = next(s for s in fig.layout.shapes if s.type == "rect")
    assert rect.fillcolor is not None


def test_pareto_empty_inputs_return_empty_figure():
    fig = charts.pareto(pd.DataFrame(), pd.DataFrame())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_bars_risk_colors_colors_each_bar_by_rating():
    series = pd.Series({"C": 0.10, "A": 0.02, "B": 0.05})
    fig = charts.bars(series, percent=True, risk_colors=True)
    assert len(fig.data) == 1
    bar = fig.data[0]
    colors_by_label = dict(zip(bar.y, bar.marker.color))
    assert colors_by_label["A"] == charts.RISK_COLORS["A"]
    assert colors_by_label["B"] == charts.RISK_COLORS["B"]
    assert colors_by_label["C"] == charts.RISK_COLORS["C"]


def test_vintage_stability_draws_one_line_per_rating_and_oot_vline():
    df = pd.DataFrame(
        {
            "safra": ["2024-01", "2024-02", "2024-01", "2024-02"],
            "Rating": ["A", "A", "B", "B"],
            "bad_rate": [0.01, 0.02, 0.05, 0.06],
        }
    )
    fig = charts.vintage_stability(
        df, time_col="safra", rating_col="Rating", rate_col="bad_rate", oot_date="2024-02"
    )
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
    names = {trace.name for trace in fig.data}
    assert names == {"A", "B"}
    assert len(fig.layout.shapes) == 1


def test_vintage_stability_without_oot_date_draws_no_vline():
    df = pd.DataFrame({"safra": ["2024-01"], "Rating": ["A"], "bad_rate": [0.01]})
    fig = charts.vintage_stability(
        df, time_col="safra", rating_col="Rating", rate_col="bad_rate"
    )
    assert len(fig.layout.shapes) == 0


def test_vintage_stability_empty_df_returns_empty_figure():
    fig = charts.vintage_stability(pd.DataFrame())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0
