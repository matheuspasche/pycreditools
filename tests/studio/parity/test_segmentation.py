"""Bancada — light business segmentation: cutoffs-per-segment (ADR 0006, issue #34).

Policy stays a single object; only the score-in-use's cutoff *value* varies per
segment value. No per-segment filters/rates/aggravation (explicitly deferred).
"""

import dataclasses

import pandas as pd
import pytest

from pycreditools.studio.analyses import (
    aggregate_funnel,
    aggregate_segment_kpis,
    policy_kpis,
    run_segmented_sim,
    segment_kpi_table,
)
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import (
    apply_cutoff_to_rows,
    build_policy,
    make_cutoff_row,
    segment_cutoff_rows,
    v14_quickfill_rows,
)


@pytest.fixture
def segmented_roles(roles):
    return dataclasses.replace(roles, segment_col="region")


@pytest.fixture
def base_rows(sample_df):
    return v14_quickfill_rows(sample_df.columns)


def test_segment_cutoff_rows_overrides_only_the_cutoff_value_per_segment(base_rows):
    score_col = "score_5"
    rows = base_rows + [make_cutoff_row(name="Corte", cutoffs={score_col: 500})]
    segment_cutoffs = {"Sudeste": 400.0, "Nordeste": 700.0}

    variants = segment_cutoff_rows(rows, score_col, segment_cutoffs)

    assert set(variants) == set(segment_cutoffs)
    for segment, value in segment_cutoffs.items():
        expected = apply_cutoff_to_rows(rows, score_col, value)
        assert variants[segment] == expected
        # Only the cutoff value changed — every other row is untouched.
        non_cutoff_original = [r for r in rows if r["type"] != "cutoff"]
        non_cutoff_variant = [r for r in variants[segment] if r["type"] != "cutoff"]
        assert non_cutoff_variant == non_cutoff_original


def test_run_segmented_sim_applies_each_segments_own_cutoff_to_its_own_slice(
    sample_df, segmented_roles, base_rows
):
    score_col = "score_5"
    rows = base_rows
    subset = population_filter(sample_df, segmented_roles, "Todos")
    segment_cutoffs = {
        "Sudeste": float(subset["score_5"].quantile(0.2)),
        "Nordeste": float(subset["score_5"].quantile(0.8)),
    }

    sims = run_segmented_sim(subset, segmented_roles, rows, score_col, segment_cutoffs)

    assert set(sims) == set(segment_cutoffs)
    for segment, value in segment_cutoffs.items():
        expected_rows = apply_cutoff_to_rows(rows, score_col, value)
        expected_slice = subset[subset["region"] == segment]
        expected_sim = build_policy(segmented_roles, expected_rows).simulate(
            expected_slice, method="analytical"
        )
        pd.testing.assert_frame_equal(sims[segment].data, expected_sim.data)

    # A tighter cutoff means a lower approval rate, all else equal.
    loose_kpis = policy_kpis(sims["Sudeste"])
    tight_kpis = policy_kpis(sims["Nordeste"])
    assert tight_kpis["approval_rate"] < loose_kpis["approval_rate"]


def test_aggregate_funnel_equals_the_sum_of_segment_funnels(
    sample_df, segmented_roles, base_rows
):
    score_col = "score_5"
    subset = population_filter(sample_df, segmented_roles, "Todos")
    segment_cutoffs = {
        "Sudeste": float(subset["score_5"].quantile(0.3)),
        "Nordeste": float(subset["score_5"].quantile(0.6)),
        "Norte": float(subset["score_5"].quantile(0.5)),
    }

    sims = run_segmented_sim(subset, segmented_roles, base_rows, score_col, segment_cutoffs)
    segment_funnels = [sim.to_funnel_dataframe() for sim in sims.values()]

    aggregate = aggregate_funnel(segment_funnels)

    for column in ("Candidates", "Passed", "Rejections"):
        # Sum stage-by-stage (matched by Stage name) rather than flattening.
        stage_sums = pd.concat(segment_funnels)[["Stage", column]].groupby(
            "Stage", sort=False
        )[column].sum()
        for stage, value in stage_sums.items():
            row = aggregate.loc[aggregate["Stage"] == stage, column]
            assert row.iloc[0] == value

    # Rates are recomputed from the summed counts, not summed/averaged themselves.
    n_total = aggregate.loc[aggregate["Stage"] == "Total", "Candidates"].iloc[0]
    for _, row in aggregate.iterrows():
        if row["Stage"] in ("Total", "Approved"):
            assert pd.isna(row["Stage_Pass_Rate"])
            assert pd.isna(row["Stage_Rej_Rate"])
        else:
            assert row["Stage_Pass_Rate"] == pytest.approx(row["Passed"] / row["Candidates"])
            assert row["Stage_Rej_Rate"] == pytest.approx(row["Rejections"] / row["Candidates"])
        assert row["Cum_Pass_Rate"] == pytest.approx(row["Passed"] / n_total)


def test_segmenting_with_the_same_cutoff_everywhere_matches_the_non_segmented_policy(
    sample_df, segmented_roles, base_rows
):
    """Toggle-off parity: segmenting with one shared cutoff value per segment behaves
    identically to a single non-segmented policy cutting at that same value."""
    score_col = "score_5"
    subset = population_filter(sample_df, segmented_roles, "Todos")
    shared_value = float(subset["score_5"].quantile(0.5))
    segment_values = subset["region"].dropna().unique().tolist()
    segment_cutoffs = {value: shared_value for value in segment_values}

    sims = run_segmented_sim(subset, segmented_roles, base_rows, score_col, segment_cutoffs)
    aggregate = aggregate_funnel([sim.to_funnel_dataframe() for sim in sims.values()])

    non_segmented_rows = apply_cutoff_to_rows(base_rows, score_col, shared_value)
    non_segmented_sim = build_policy(segmented_roles, non_segmented_rows).simulate(
        subset, method="analytical"
    )
    expected_funnel = non_segmented_sim.to_funnel_dataframe()

    pd.testing.assert_frame_equal(
        aggregate.reset_index(drop=True), expected_funnel.reset_index(drop=True)
    )


def test_segment_kpi_table_has_one_row_per_segment_matching_policy_kpis(
    sample_df, segmented_roles, base_rows
):
    score_col = "score_5"
    subset = population_filter(sample_df, segmented_roles, "Todos")
    segment_cutoffs = {
        "Sudeste": float(subset["score_5"].quantile(0.3)),
        "Nordeste": float(subset["score_5"].quantile(0.7)),
    }
    sims = run_segmented_sim(subset, segmented_roles, base_rows, score_col, segment_cutoffs)

    table = segment_kpi_table(sims)

    assert set(table["segment"]) == set(segment_cutoffs)
    for segment, sim in sims.items():
        expected = policy_kpis(sim)
        row = table[table["segment"] == segment].iloc[0]
        assert row["approval_rate"] == pytest.approx(expected["approval_rate"])
        assert row["approved_volume"] == pytest.approx(expected["approved_volume"])


def test_aggregate_segment_kpis_equals_the_combined_population_outcome(
    sample_df, segmented_roles, base_rows
):
    score_col = "score_5"
    subset = population_filter(sample_df, segmented_roles, "Todos")
    segment_cutoffs = {
        "Sudeste": float(subset["score_5"].quantile(0.3)),
        "Nordeste": float(subset["score_5"].quantile(0.7)),
    }
    sims = run_segmented_sim(subset, segmented_roles, base_rows, score_col, segment_cutoffs)

    aggregate = aggregate_segment_kpis(sims)

    combined = pd.concat([sim.data for sim in sims.values()], ignore_index=True)
    expected_approval_rate = float(combined["new_approval"].mean())
    expected_volume = float(combined["new_approval"].sum())

    assert aggregate["approval_rate"] == pytest.approx(expected_approval_rate)
    assert aggregate["approved_volume"] == pytest.approx(expected_volume)
