"""The noise discipline of `tests/noise_discipline.py` and `tests/conftest.py` (§6, #158).

A test that compares an engine number with a number computed by hand declares three things or
it is a flake: the seed comes from the fixture, the tolerance is in units of noise with k and n
declared, and a bias criterion runs rounds. These tests pin the helpers that make the three
declarations cheap, what "exact" and "reproducible" mean, and the guards that keep
`tests/engine/` and `src/pycreditools/engine/` off the global streams.
"""

from __future__ import annotations

import math
import random
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from noise_discipline import (
    assert_exact,
    assert_reproducible,
    assert_unbiased,
    assert_within_k_sd,
    derive_seed,
    derive_seeds,
    find_unkeyed_draws,
    measure_sd,
    no_global_draws,
    t_two_sided_tail,
)

from pycreditools.engine import CreditPolicy, DataSchema, Premise, Study

TESTS = Path(__file__).parent
ENGINE_SOURCE = TESTS.parent / "src" / "pycreditools" / "engine"


def _noise(seed: int, scale: float) -> float:
    return float(np.random.default_rng(seed).normal(0.0, scale))


# ── 1. Seeds are derived ─────────────────────────────────────────────────


def test_the_seed_fixture_derives_from_the_node_id(seed, request, seed_offset):
    assert seed == derive_seed(request.node.nodeid, offset=seed_offset)


def test_derive_seed_is_crc32_and_an_offset_is_another_realization():
    assert derive_seed("a/b.py::t") == zlib.crc32(b"a/b.py::t")
    assert derive_seed("a/b.py::t", offset=1) != derive_seed("a/b.py::t")
    assert derive_seed("a/b.py::t", offset=1) == derive_seed("a/b.py::t", offset=1)


def test_derived_seeds_are_distinct_plain_ints(seeds):
    got = seeds(50)
    assert len(set(got)) == 50
    assert all(type(s) is int and 0 <= s < 2**32 for s in got)
    assert got == seeds(50)


def test_derived_seeds_build_a_study(seed, seeds):
    """`Study` takes a plain int only (`study.py:51`); a `np.uint32` would be refused."""
    premise = Premise(take_up=0.7, outcome_from="market_default")
    for s in [seed, *seeds(5), *derive_seeds("module", 3)]:
        assert Study(DataSchema(), CreditPolicy(), premise, seed=s).seed == s


def test_rng_is_a_generator_on_the_test_seed(seed, rng):
    with no_global_draws():
        got = rng.random(3)
    np.testing.assert_array_equal(got, np.random.default_rng(seed).random(3))


@pytest.mark.parametrize("offset", [-1, 1.5, True])
def test_an_offset_is_a_non_negative_int(offset):
    with pytest.raises(ValueError, match="offset"):
        derive_seed("x", offset=offset)


# ── Exact, for a float ───────────────────────────────────────────────────


def test_exact_absorbs_the_rounding_of_a_sum_and_nothing_more():
    assert_exact(0.1 + 0.2, 0.3, terms=2)
    with pytest.raises(AssertionError, match="rounding of 2 terms"):
        assert_exact(0.3 + 1e-12, 0.3, terms=2)


def test_exact_absorbs_the_rounding_of_a_running_total(rng):
    """Ticket 10's running totals round more than a pairwise sum does, and still sit inside
    the floor — a fixed 1e-12 would have failed this exact path."""
    n = 1_000_000
    weights = np.full(n, 0.7)
    bad = (rng.random(n) < 0.05).astype(float)
    running = np.cumsum(weights * bad)[-1] / np.cumsum(weights)[-1]
    fsum = math.fsum(weights * bad) / math.fsum(weights)
    assert running != fsum
    assert_exact(running, fsum, terms=n)


def test_exact_declares_its_terms():
    with pytest.raises(TypeError, match="terms"):
        assert_exact(0.3, 0.3)
    with pytest.raises(ValueError, match="terms"):
        assert_exact(0.3, 0.3, terms=0)


# ── 2. Tolerance in units of noise ───────────────────────────────────────

SD_3MM = 0.0003  # §6: "O sd medido a 3 MM é 0,022–0,039 p.p."


def test_the_band_passes_inside_k_and_fails_outside_naming_k_and_both_ns():
    se = SD_3MM * math.sqrt(3_000_000 / 200_000)
    assert_within_k_sd(0.05 + 3.9 * se, 0.05, sd=SD_3MM, at_n=3_000_000, n=200_000, k=4)
    with pytest.raises(
        AssertionError, match=r"4\.\d\d sd apart, allowed k=4 at n=200000 .*n=3000000"
    ):
        assert_within_k_sd(0.05 + 4.1 * se, 0.05, sd=SD_3MM, at_n=3_000_000, n=200_000, k=4)


def test_a_band_measured_at_3mm_holds_at_200k_where_an_absolute_tolerance_fails():
    """§6: "uma tolerância absoluta escolhida a 3 MM reprova sozinha a 200k"."""
    absolute_at_3mm = 4 * SD_3MM
    gap_at_200k = 2 * SD_3MM * math.sqrt(3_000_000 / 200_000)  # a correct path, 2 sd out
    assert gap_at_200k > absolute_at_3mm
    assert_within_k_sd(0.05 + gap_at_200k, 0.05, sd=SD_3MM, at_n=3_000_000, n=200_000, k=4)
    with pytest.raises(AssertionError):
        assert_within_k_sd(0.05 + gap_at_200k, 0.05, sd=SD_3MM, at_n=3_000_000, n=3_000_000, k=4)


@pytest.mark.parametrize("missing", ["sd", "at_n", "n", "k"])
def test_the_band_has_no_defaults_to_hide_behind(missing):
    declared = {"sd": SD_3MM, "at_n": 3_000_000, "n": 200_000, "k": 4}
    del declared[missing]
    with pytest.raises(TypeError, match=missing):
        assert_within_k_sd(0.05, 0.05, **declared)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("sd", 0.0),
        ("sd", -SD_3MM),
        ("sd", math.inf),
        ("sd", math.nan),
        ("k", 0),
        ("k", -1),
        ("k", math.inf),
        ("k", math.nan),
        ("n", 0),
        ("n", 1.5),
        ("at_n", 0),
        ("at_n", True),
    ],
)
def test_the_band_refuses_values_that_are_no_band(name, value):
    declared = {"sd": SD_3MM, "at_n": 3_000_000, "n": 200_000, "k": 4, name: value}
    with pytest.raises(ValueError, match=name):
        assert_within_k_sd(0.05, 0.05, **declared)


def test_the_band_refuses_a_non_finite_reading():
    with pytest.raises(ValueError, match="observed"):
        assert_within_k_sd(math.nan, 0.05, sd=SD_3MM, at_n=3_000_000, n=200_000, k=4)


def test_the_band_takes_numpy_integers():
    assert_within_k_sd(0.05, 0.05, sd=SD_3MM, at_n=np.int64(3_000_000), n=np.int32(200_000), k=4)


def test_measure_sd_is_the_sd_of_the_rounds(seeds):
    rounds = seeds(40)
    fn = lambda s: 0.05 + _noise(s, 0.01)  # noqa: E731
    assert measure_sd(fn, seeds=rounds) == pytest.approx(np.std([fn(s) for s in rounds], ddof=1))


def test_measure_sd_needs_twenty_rounds(seeds):
    with pytest.raises(ValueError, match="at least 20"):
        measure_sd(lambda s: _noise(s, 0.01), seeds=seeds(19))


def test_measure_sd_refuses_a_number_that_does_not_draw(seeds):
    with pytest.raises(ValueError, match="assert_exact"):
        measure_sd(lambda s: 0.05, seeds=seeds(20))


# ── 3. Rounds where the criterion is bias ────────────────────────────────


@pytest.mark.parametrize(
    ("k", "df", "tail"),
    [
        (1.0, 1, 0.5),  # Cauchy: P(|T| > 1) = 1/2
        (math.sqrt(2), 2, 1 - math.sqrt(2) / 2),
        (3.0, 7, 0.0199),
        (4.0, 7, 0.0052),
        (3.0, 10_000, 0.0027),  # the normal's 3-sigma tail
    ],
)
def test_the_student_t_tail(k, df, tail):
    assert t_two_sided_tail(k, df) == pytest.approx(tail, abs=1e-4)


@pytest.mark.parametrize(("rounds", "k"), [(2, 4), (3, 4), (5, 3), (8, 3)])
def test_a_k_that_errs_more_than_one_percent_at_these_rounds_is_refused(seeds, rounds, k):
    with pytest.raises(ValueError, match=r"raise k or the rounds"):
        assert_unbiased(
            lambda s: 0.25, lambda s: 0.25, seeds=seeds(rounds), k=k, paired=True, terms=1
        )


def test_the_reading_carries_its_false_alarm_rate(seeds):
    reading = assert_unbiased(
        lambda s: 0.25, lambda s: 0.25, seeds=seeds(8), k=4, paired=True, terms=1
    )
    assert reading.false_alarm == pytest.approx(0.0052, abs=1e-4)


def test_paired_rounds_share_the_seed_and_unpaired_rounds_do_not(seeds):
    rounds = seeds(8)
    for paired in (True, False):
        engine_seeds, hand_seeds = [], []
        assert_unbiased(
            lambda s: engine_seeds.append(s) or _noise(s, 0.01),
            lambda s: hand_seeds.append(s) or _noise(s, 0.01),
            seeds=rounds,
            k=4,
            paired=paired,
            terms=1,
        )
        assert engine_seeds == rounds
        if paired:
            assert hand_seeds == rounds
        else:
            assert len(set(hand_seeds)) == 8 and not set(hand_seeds) & set(rounds)


def test_unpaired_rounds_pass_an_unbiased_path(seeds):
    """The #149 shape: engine and hand each on their own draws."""
    reading = assert_unbiased(
        lambda s: 0.25 + _noise(s, 0.01),
        lambda s: 0.25 + _noise(s, 0.01),
        seeds=seeds(16),
        k=4,
        paired=False,
        terms=1,
    )
    assert abs(reading.z) <= 4 and not reading.paired


def test_unpaired_rounds_catch_a_bias_larger_than_their_standard_error(seeds):
    with pytest.raises(AssertionError, match=r"bias .* sd .* k=4 over 16 rounds \(unpaired"):
        assert_unbiased(
            lambda s: 0.28 + _noise(s, 0.01),
            lambda s: 0.25 + _noise(s, 0.01),
            seeds=seeds(16),
            k=4,
            paired=False,
            terms=1,
        )


def _shared_draw_path(bias: float):
    """A stand-in for a path under test that consumes the keyed draw (0.01, the same for the
    hand side on the same seed) plus a residual of its own (0.001)."""
    return lambda s: 0.25 + bias + _noise(s, 0.01) + _noise(s + 7, 0.001)


def _shared_draw_hand(s: int) -> float:
    return 0.25 + _noise(s, 0.01) + _noise(s + 13, 0.001)


def test_pairing_draws_its_power_from_the_shared_draw_only(seeds):
    """0.004 of bias under 0.01 of draw noise, 8 rounds. Paired on the seed, the shared draw
    cancels and the bias reads as bias. Unpaired — which is what pairing becomes when the hand
    does not consume the engine's draw — the same bias sits inside the noise and passes."""
    with pytest.raises(AssertionError, match=r"k=4 over 8 rounds \(paired"):
        assert_unbiased(
            _shared_draw_path(0.004), _shared_draw_hand, seeds=seeds(8), k=4, paired=True, terms=1
        )
    reading = assert_unbiased(
        _shared_draw_path(0.004), _shared_draw_hand, seeds=seeds(8), k=4, paired=False, terms=1
    )
    assert abs(reading.z) < 4


@pytest.mark.parametrize("paired", [True, False])
def test_an_exact_path_never_reads_as_bias(seeds, paired):
    reading = assert_unbiased(
        lambda s: 0.1 + 0.2, lambda s: 0.3, seeds=seeds(8), k=4, paired=paired, terms=2
    )
    assert reading.gap == 0.0 and reading.z == 0.0


@pytest.mark.parametrize("paired", [True, False])
def test_a_constant_gap_is_bias_even_without_noise(seeds, paired):
    with pytest.raises(AssertionError, match="bias"):
        assert_unbiased(lambda s: 0.26, lambda s: 0.25, seeds=seeds(8), k=4, paired=paired, terms=1)


def test_the_rounds_are_declared_and_sound(seeds):
    with pytest.raises(ValueError, match="one round"):
        assert_unbiased(lambda s: 0.25, lambda s: 0.25, seeds=seeds(1), k=4, paired=True, terms=1)
    with pytest.raises(ValueError, match="repeat"):
        assert_unbiased(lambda s: 0.25, lambda s: 0.25, seeds=[1] * 8, k=4, paired=True, terms=1)
    with pytest.raises(TypeError, match="paired"):
        assert_unbiased(lambda s: 0.25, lambda s: 0.25, seeds=seeds(8), k=4, paired=1, terms=1)
    with pytest.raises(TypeError, match="paired"):
        assert_unbiased(lambda s: 0.25, lambda s: 0.25, seeds=seeds(8), k=4, terms=1)
    with pytest.raises(ValueError, match="engine"):
        assert_unbiased(
            lambda s: math.nan, lambda s: 0.25, seeds=seeds(8), k=4, paired=True, terms=1
        )


# ── Reproduces under the seed ────────────────────────────────────────────


def test_a_keyed_frame_reproduces():
    def run(seed):
        draws = np.random.default_rng(seed).random(5)
        return pd.DataFrame({"u": draws, "flag": draws < 0.5}), float(draws.sum())

    assert_reproducible(run, 7)


def test_a_global_draw_does_not_reproduce():
    with pytest.raises(AssertionError):
        assert_reproducible(lambda seed: np.random.random(3), 7)


def test_a_dtype_that_changes_between_runs_does_not_reproduce():
    calls = []

    def run(seed):
        calls.append(seed)
        return np.array([1]) if len(calls) == 1 else np.array([1.0])

    with pytest.raises(AssertionError, match="int64 vs float64|int32 vs float64"):
        assert_reproducible(run, 7)


# ── The global streams, at run time ──────────────────────────────────────


def test_no_global_draws_passes_a_block_that_does_not_draw():
    with no_global_draws():
        np.random.default_rng(0).random()


@pytest.mark.parametrize(
    ("touch", "stream"),
    [
        (lambda: np.random.random(), "np.random"),
        (lambda: np.random.seed(0), "np.random"),
        (lambda: random.random(), "random"),
    ],
    ids=["numpy-draw", "numpy-reseed", "stdlib-draw"],
)
def test_no_global_draws_fails_a_block_that_touches_a_stream(touch, stream):
    np_state, py_state = np.random.get_state(), random.getstate()
    try:
        with pytest.raises(AssertionError, match=f"global {stream} stream moved"):
            with no_global_draws():
                touch()
    finally:
        np.random.set_state(np_state)
        random.setstate(py_state)


def _harness(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    """The real conftest and module, copied; the child prints UTF-8 whatever the console."""
    pytester.makeconftest((TESTS / "conftest.py").read_text(encoding="utf-8"))
    pytester.makepyfile(
        noise_discipline=(TESTS / "noise_discipline.py").read_text(encoding="utf-8")
    )
    monkeypatch.setenv("PYTHONUTF8", "1")


def test_engine_tests_error_when_they_draw_without_a_key(pytester, monkeypatch):
    """§4.6, "Nenhum np.random global sobra no núcleo": under `tests/engine/`, a global draw or
    reseed — numpy or stdlib, in the test, a function fixture or a module fixture — errors, and
    an unseeded `default_rng()` fails where it is called. The old suite is not policed."""
    _harness(pytester, monkeypatch)
    pytester.mkdir("engine")
    pytester.makepyfile(
        **{
            "engine/test_offenders": """
                import random

                import numpy as np
                import pytest

                @pytest.fixture
                def drawn_at_setup():
                    return np.random.random()

                def test_draws_globally():
                    np.random.random()

                def test_reseeds_globally():
                    np.random.seed(0)

                def test_draws_from_stdlib_random():
                    random.random()

                def test_draws_in_a_fixture(drawn_at_setup):
                    pass

                def test_builds_an_unseeded_generator():
                    np.random.default_rng()
            """,
            "engine/test_module_fixture": """
                import numpy as np
                import pytest

                @pytest.fixture(scope="module")
                def expensive_run():
                    return np.random.random()

                def test_shares_a_module_run(expensive_run):
                    pass
            """,
            "engine/test_keyed": """
                import numpy as np
                import pytest
                from noise_discipline import derive_seed

                @pytest.fixture(scope="module")
                def expensive_run(request, seed_offset):
                    seed = derive_seed(request.node.nodeid, offset=seed_offset)
                    return np.random.default_rng(seed).random()

                def test_draws_from_the_fixture(rng):
                    rng.random()

                def test_shares_a_keyed_module_run(expensive_run):
                    pass
            """,
            "test_old_suite": """
                import numpy as np

                def test_the_old_suite_may_still_draw_globally():
                    np.random.random()
            """,
        }
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=7, failed=1, errors=5)
    for name in (
        "test_draws_globally",
        "test_reseeds_globally",
        "test_draws_from_stdlib_random",
        "test_draws_in_a_fixture",
    ):
        result.stdout.fnmatch_lines([f"ERROR engine/test_offenders.py::{name} - *"])
    result.stdout.fnmatch_lines(
        [
            "FAILED engine/test_offenders.py::test_builds_an_unseeded_generator - *",
            "ERROR engine/test_module_fixture.py::test_shares_a_module_run - *",
        ]
    )
    for verdict in ("FAILED", "ERROR"):
        for clean in ("engine/test_keyed.py", "test_old_suite.py"):
            result.stdout.no_fnmatch_line(f"{verdict} {clean}::*")


def test_seed_offset_moves_every_seed_and_shows_in_the_header(pytester, monkeypatch):
    _harness(pytester, monkeypatch)
    pytester.makepyfile(
        test_seeded="""
            from noise_discipline import derive_seed

            def test_seed_follows_the_offset(seed, request):
                assert seed == derive_seed(request.node.nodeid, offset=3)
        """
    )
    result = pytester.runpytest_subprocess("--seed-offset", "3")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["seed offset: 3 *"])


# ── The global streams, in source ────────────────────────────────────────


def test_the_engine_source_has_no_unkeyed_draw():
    sources = sorted(ENGINE_SOURCE.rglob("*.py"))
    assert sources, f"no source under {ENGINE_SOURCE}: the tripwire would pass empty"
    found = [
        hit
        for path in sources
        for hit in find_unkeyed_draws(path.read_text(encoding="utf-8"), str(path))
    ]
    assert found == []


@pytest.mark.parametrize(
    "source",
    [
        "import random",
        "from random import random",
        "import numpy as np\nnp.random.random(3)",
        "import numpy as np\nnp.random.seed(0)",
        "import numpy as np\nnp.random.default_rng()",
        "import numpy as np\nnp.random.default_rng(None)",
        "import numpy as np\nnp.random.default_rng(seed=None)",
        "import numpy as np\nnp.random.RandomState(0)",
        "import numpy as np\nnp.random.Generator(np.random.PCG64())",
        "import numpy as np\ndraw = np.random.random",
        "import numpy\nnumpy.random.shuffle(x)",
        "import numpy.random as npr\nnpr.permutation(5)",
        "from numpy import random as npr\nnpr.choice(3)",
        "from numpy.random import shuffle",
        "from numpy.random import default_rng\ndefault_rng()",
        "from numpy.random import SeedSequence as SS\nSS()",
    ],
)
def test_the_tripwire_catches_each_unkeyed_draw(source):
    assert find_unkeyed_draws(source)


@pytest.mark.parametrize(
    "source",
    [
        "import numpy as np\nnp.random.default_rng(seed)",
        "import numpy as np\nnp.random.Generator(np.random.PCG64(seed))",
        "import numpy as np\nnp.random.SeedSequence([seed, position])",
        "from numpy.random import default_rng\ndefault_rng(key)",
        "rng.random(3)",
        "import numpy as np\ndef f(rng: np.random.Generator): return rng.permutation(3)",
    ],
)
def test_the_tripwire_passes_keyed_draws(source):
    assert find_unkeyed_draws(source) == []
