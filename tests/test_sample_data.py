"""Invariants of the two canonical bases (#74)."""

import pandas as pd
import pytest

from pycreditools import (
    LEGACY_APPROVAL_QUANTILE,
    generate_sample_data,
    generate_standalone_sample_data,
)

FORBIDDEN_COLS = {"take_up_rate", "conversion_rate", "score_decile"}
INCUMBENT_COLS = {"approved", "legacy_score", "hired", "passed_antifraud", "sample"}


@pytest.fixture(scope="module")
def incumbent() -> pd.DataFrame:
    return generate_sample_data(n_applicants=20_000, seed=42)


@pytest.fixture(scope="module")
def standalone() -> pd.DataFrame:
    return generate_standalone_sample_data(n_applicants=5_000, seed=42)


# --- incumbent base ----------------------------------------------------------------


def test_incumbent_has_the_documented_columns(incumbent):
    expected = {
        "applicant_id",
        "safra",
        "region",
        "age",
        "income",
        "employment",
        "cpf_valido",
        "vl_negativacao",
        "vl_vencido_scr",
        "vl_protestos",
        "legacy_score",
        "score_2",
        "score_3",
        "score_4",
        "score_5",
        "approved",
        "passed_antifraud",
        "hired",
        "actual_default",
        "market_default",
        "sample",
    }
    assert set(incumbent.columns) == expected


def test_actual_default_is_masked_exactly_where_nobody_contracted(incumbent):
    masked = incumbent["actual_default"].isna()
    assert masked.equals(incumbent["hired"] == 0)
    assert masked.any(), "the masking invariant is vacuous if everyone contracted"


def test_contracted_outcomes_are_zero_or_one(incumbent):
    observed = incumbent.loc[incumbent["hired"] == 1, "actual_default"]
    assert set(observed.unique()) <= {0.0, 1.0}


def test_market_default_is_observed_and_binary_for_every_row(incumbent):
    assert incumbent["market_default"].notna().all()
    assert set(incumbent["market_default"].unique()) == {0, 1}


def test_market_default_is_wider_than_the_book_but_tracks_the_same_risk(incumbent):
    contracted = incumbent[incumbent["hired"] == 1]
    book_rate = contracted["actual_default"].mean()
    market_rate = contracted["market_default"].mean()
    # The market is wider than one lender's product, so a contracted client defaults
    # somewhere in the market more often than on this book — but not implausibly so.
    assert book_rate < market_rate < 4 * book_rate
    # The flag must track the same risk the scores rank: higher score, less market default.
    assert incumbent["market_default"].corr(incumbent["score_5"]) < -0.3


def test_no_propensity_or_take_up_column(incumbent):
    assert FORBIDDEN_COLS.isdisjoint(incumbent.columns)


def test_take_up_falls_as_score_rises(incumbent):
    # Take-up is only observable among the approved, who sit in the top slice of the
    # score distribution — so the gradient measured here is a compressed view of the
    # 0.95 → 0.41 rule the generator applies over the whole base.
    approved = incumbent[incumbent["approved"] == 1].copy()
    approved["decile"] = pd.qcut(approved["score_5"].rank(method="first"), q=10, labels=False)
    take_up = approved.groupby("decile")["hired"].mean()
    assert take_up.iloc[0] > take_up.iloc[-1] + 0.15
    # Adverse selection is monotone in intent; allow decile-level sampling wobble.
    assert take_up.corr(pd.Series(take_up.index, index=take_up.index)) < -0.8


def test_approval_rate_is_around_the_incumbent_cut(incumbent):
    assert 0.15 < incumbent["approved"].mean() < 0.25


def test_legacy_cut_is_recomputable_by_the_caller(incumbent):
    cut = incumbent["legacy_score"].quantile(LEGACY_APPROVAL_QUANTILE)
    approved = incumbent[incumbent["approved"] == 1]
    assert (approved["legacy_score"] >= cut).all()


def test_antifraud_is_independent_of_risk(incumbent):
    rate = incumbent["passed_antifraud"].mean()
    assert 0.88 < rate < 0.92
    by_flag = incumbent.groupby("passed_antifraud")["score_5"].mean()
    assert abs(by_flag.loc[0] - by_flag.loc[1]) < 10


def test_sample_splits_dev_and_oot(incumbent):
    assert set(incumbent["sample"].unique()) == {"DEV", "OOT"}


def test_seed_makes_it_reproducible():
    a = generate_sample_data(n_applicants=500, seed=7)
    b = generate_sample_data(n_applicants=500, seed=7)
    pd.testing.assert_frame_equal(a, b)


# --- standalone base ---------------------------------------------------------------


def test_standalone_carries_no_incumbent_columns(standalone):
    assert INCUMBENT_COLS.isdisjoint(standalone.columns)
    assert FORBIDDEN_COLS.isdisjoint(standalone.columns)


def test_standalone_outcome_is_observed_for_everyone(standalone):
    assert standalone["actual_default"].notna().all()
    assert set(standalone["actual_default"].unique()) == {0, 1}


def test_standalone_keeps_features_and_scores(standalone):
    expected = {
        "applicant_id",
        "safra",
        "region",
        "age",
        "income",
        "employment",
        "cpf_valido",
        "vl_negativacao",
        "vl_vencido_scr",
        "vl_protestos",
        "score_2",
        "score_3",
        "score_4",
        "score_5",
        "actual_default",
    }
    assert set(standalone.columns) == expected


def test_standalone_has_no_market_default(standalone):
    # The bureau flag exists to see the outcome of applicants you rejected. This base
    # rejected nobody, so the column would be answering a question it cannot be asked.
    assert "market_default" not in standalone.columns


def test_standalone_seed_makes_it_reproducible():
    a = generate_standalone_sample_data(n_applicants=500, seed=7)
    b = generate_standalone_sample_data(n_applicants=500, seed=7)
    pd.testing.assert_frame_equal(a, b)
