"""The noise discipline of `tests/conftest.py` (§6 "Higiene de semente", ticket 2, #158).

A test that compares an engine number with a number computed by hand declares three things or
it is a flake: the seed comes from the fixture, the tolerance is in units of noise with k and n
declared, and a bias criterion runs paired rounds. #149 spent 16 runs at 3 MM to learn that a
4.1 sd reading was not bias — one round against one round would have failed a correct path.

These tests pin the helpers that make the three declarations cheap, and the guard that keeps
`tests/engine/` off the global `np.random` stream.
"""

from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np
import pytest

CONFTEST = Path(__file__).with_name("conftest.py")


# ── 1. The seed comes from the fixture ───────────────────────────────────


def test_the_seed_derives_from_the_node_id(seed, request):
    """Stable across runs and machines, distinct between tests, and a valid `Study.seed`."""
    assert seed == zlib.crc32(request.node.nodeid.encode())
    assert type(seed) is int and 0 <= seed < 2**32


def test_rng_is_a_generator_on_the_test_seed(seed, rng, no_global_draws):
    with no_global_draws():
        got = rng.random(3)
    np.testing.assert_array_equal(got, np.random.default_rng(seed).random(3))


# ── 2. Tolerance in units of noise, k and n declared ─────────────────────


def test_within_k_sd_passes_inside_k_standard_errors(assert_within_k_sd):
    se = 0.4 / np.sqrt(10_000)
    assert_within_k_sd(0.30 + 2.9 * se, 0.30, per_row_sd=0.4, n=10_000, k=3)


def test_within_k_sd_fails_outside_and_names_k_and_n(assert_within_k_sd):
    se = 0.4 / np.sqrt(10_000)
    with pytest.raises(AssertionError, match=r"3\.1\d sd .* k=3 .* n=10000"):
        assert_within_k_sd(0.30 + 3.15 * se, 0.30, per_row_sd=0.4, n=10_000, k=3)


def test_the_same_gap_passes_at_small_n_and_fails_at_large_n(assert_within_k_sd):
    """The band scales with 1/sqrt(n): a gap that is noise at 200k is signal at 3 MM. An
    absolute tolerance chosen at one n is wrong at the other — which is why there is none."""
    gap = 0.002
    assert_within_k_sd(0.10 + gap, 0.10, per_row_sd=0.3, n=200_000, k=3)
    with pytest.raises(AssertionError):
        assert_within_k_sd(0.10 + gap, 0.10, per_row_sd=0.3, n=3_000_000, k=3)


@pytest.mark.parametrize("missing", ["per_row_sd", "n", "k"])
def test_within_k_sd_has_no_defaults_to_hide_behind(assert_within_k_sd, missing):
    declared = {"per_row_sd": 0.4, "n": 1_000, "k": 3}
    del declared[missing]
    with pytest.raises(TypeError, match=missing):
        assert_within_k_sd(0.3, 0.3, **declared)


def test_within_k_sd_refuses_zero_noise(assert_within_k_sd):
    """A number with no noise is compared exactly, not within a band of width zero."""
    with pytest.raises(ValueError, match="exact"):
        assert_within_k_sd(0.3, 0.3, per_row_sd=0.0, n=1_000, k=3)


# ── 3. Paired rounds where the criterion is bias ─────────────────────────


def _noise(seed: int, scale: float) -> float:
    return float(np.random.default_rng(seed).normal(0.0, scale))


def test_paired_rounds_share_the_seed_within_a_pair(assert_unbiased):
    engine_seeds, hand_seeds = [], []

    def engine(s):
        engine_seeds.append(s)
        return _noise(s, 0.01)

    def hand(s):
        hand_seeds.append(s)
        return _noise(s, 0.01)

    assert_unbiased(engine, hand, pairs=8, k=3)
    assert engine_seeds == hand_seeds
    assert len(set(engine_seeds)) == 8


def _engine(bias: float):
    """A path that faces the seed's draw (0.01, shared with the hand side when paired on the
    seed) plus a residual of its own (0.001) — the shape a keyed draw gives."""
    return lambda s: 0.25 + bias + _noise(s, 0.01) + _noise(s + 7, 0.001)


def _hand(s: int) -> float:
    return 0.25 + _noise(s, 0.01) + _noise(s + 13, 0.001)


def test_paired_rounds_pass_an_unbiased_noisy_path(assert_unbiased):
    """Engine and hand disagree by noise every round, and by nothing on average."""
    result = assert_unbiased(_engine(0.0), _hand, pairs=8, k=3)
    assert abs(result.z) <= 3


def test_paired_rounds_catch_a_bias_hidden_in_single_round_noise(assert_unbiased):
    """0.004 of bias under 0.01 of draw noise. One engine round against one hand round on
    unshared draws reads it well under 1 sd; eight rounds paired on the seed cancel the shared
    draw and read it as bias."""
    unpaired_gap = _engine(0.004)(1) - _hand(2)
    assert abs(unpaired_gap - 0.004) < 0.03  # the bias is inside single-round noise
    with pytest.raises(AssertionError, match=r"bias .* sd .* k=3 .* 8 pairs"):
        assert_unbiased(_engine(0.004), _hand, pairs=8, k=3)


def test_paired_rounds_that_agree_exactly_are_unbiased(assert_unbiased):
    result = assert_unbiased(lambda s: _noise(s, 0.01), lambda s: _noise(s, 0.01), pairs=4, k=3)
    assert result.mean == 0.0


def test_a_constant_nonzero_gap_is_bias_even_without_noise(assert_unbiased):
    with pytest.raises(AssertionError, match="bias"):
        assert_unbiased(lambda s: 0.26, lambda s: 0.25, pairs=4, k=3)


def test_one_pair_cannot_separate_bias_from_noise(assert_unbiased):
    with pytest.raises(ValueError, match="pairs"):
        assert_unbiased(lambda s: 0.25, lambda s: 0.25, pairs=1, k=3)


# ── The global stream ────────────────────────────────────────────────────


def test_no_global_draws_passes_a_block_that_does_not_draw(no_global_draws):
    with no_global_draws():
        np.random.default_rng(0).random()


@pytest.mark.parametrize(
    "touch", [lambda: np.random.random(), lambda: np.random.seed(0)], ids=["draw", "reseed"]
)
def test_no_global_draws_fails_a_block_that_touches_the_stream(no_global_draws, touch):
    state = np.random.get_state()
    try:
        with pytest.raises(AssertionError, match="global"):
            with no_global_draws():
                touch()
    finally:
        np.random.set_state(state)


def test_engine_tests_fail_when_they_touch_the_global_stream(pytester):
    """`Nenhum np.random global sobra no núcleo` (§4.6): under `tests/engine/` a test that
    draws from, or reseeds, the global stream fails — whether the call is in the test or in
    the engine under test. The old suite outside `tests/engine/` is not policed; it dies at
    the contraction (ticket 16)."""
    pytester.makeconftest(CONFTEST.read_text(encoding="utf-8"))
    pytester.mkdir("engine")
    pytester.makepyfile(
        **{
            "engine/test_draws": """
                import numpy as np

                def test_draws_globally():
                    np.random.random()

                def test_reseeds_globally():
                    np.random.seed(0)

                def test_draws_from_the_fixture(rng):
                    rng.random()
            """,
            "test_old_suite": """
                import numpy as np

                def test_the_old_suite_may_still_draw_globally():
                    np.random.random()
            """,
        }
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2, failed=2)
    result.stdout.fnmatch_lines(["*_ test_draws_globally _*", "*global np.random stream moved*"])
