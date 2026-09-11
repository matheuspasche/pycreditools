"""Noise discipline for the core suite (§6 "Higiene de semente — pré-requisito, não higiene").

Every test that compares an engine number with a number computed by hand declares three
things, or it is a flake:

1. **Seed policy** — the seed comes from the `seed` fixture (or the `rng` built on it), never
   from a global `np.random.seed`. Under `tests/engine/` the global stream is policed: a test
   that draws from it or reseeds it fails, whether the call sits in the test or in the engine
   under test (§4.6: no global `np.random` is left in the core).
2. **Tolerance in units of noise** — `assert_within_k_sd`, with k and n declared. The sd
   measured at 3 MM is 0.022–0.039 p.p. and scales with 1/sqrt(n): an absolute tolerance
   chosen at 3 MM fails on its own at 200k.
3. **Paired rounds where the criterion is bias** — `assert_unbiased`. One round against one
   round does not separate bias from noise: #149 read 4.1 sd on a correct path, and it took
   8 paired rounds against 8 hand simulations (0.2 / 1.2 / 0.9 standard errors) to clear it.

`tests/studio/conftest.py` is the Studio's (ticket 13); this one is the core's.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pytest

pytest_plugins = ["pytester"]

ENGINE_TESTS = Path(__file__).parent / "engine"


# ── 1. The seed comes from the fixture ───────────────────────────────────


@pytest.fixture
def seed(request: pytest.FixtureRequest) -> int:
    """The test's seed: the CRC-32 of its node id.

    Stable across runs and machines, distinct between tests (parametrized cases included),
    and a valid `Study.seed`. Renaming a test changes its seed — a test that passes on one
    seed only was testing a realization, not the path, and `assert_unbiased` is the cure.
    """
    return zlib.crc32(request.node.nodeid.encode())


@pytest.fixture
def rng(seed: int) -> np.random.Generator:
    """A `Generator` on the test's seed. Never the global stream."""
    return np.random.default_rng(seed)


# ── 2. Tolerance in units of noise, k and n declared ─────────────────────


def _within_k_sd(observed: float, expected: float, *, per_row_sd: float, n: int, k: float) -> None:
    """`observed` is within k standard errors of `expected`, the standard error being
    `per_row_sd / sqrt(n)`.

    `per_row_sd` is the dispersion one row contributes to the gap — `sqrt(p * (1 - p))` for a
    rate against an exact `expected` — and it does not move with n; the band does. When the
    hand side is sampled too, on draws of its own, the gap carries both: pass `sqrt(2)` times
    the per-row sd. `n` is the rows the number is taken over — the contracted rows for a
    default rate, not the base. No argument has a default: an undeclared k or n is how an
    absolute tolerance comes back.
    """
    if not per_row_sd > 0:
        raise ValueError(
            f"per_row_sd={per_row_sd!r}: a number with no noise is compared exactly, "
            "not within a band of width zero"
        )
    if n < 1 or not k > 0:
        raise ValueError(f"n={n!r} and k={k!r} must be positive")
    se = per_row_sd / math.sqrt(n)
    z = (observed - expected) / se
    assert abs(z) <= k, (
        f"{observed!r} vs {expected!r}: {abs(z):.2f} sd apart, allowed k={k} "
        f"at n={n} (per-row sd {per_row_sd}, se {se:.3g})"
    )


@pytest.fixture
def assert_within_k_sd() -> Callable[..., None]:
    return _within_k_sd


# ── 3. Paired rounds where the criterion is bias ─────────────────────────


class Paired(NamedTuple):
    """The paired-rounds reading: mean of `engine − hand` over the pairs, its standard
    error, and the distance from zero in standard errors (0 when every pair agrees)."""

    mean: float
    se: float
    z: float
    pairs: int


@pytest.fixture
def assert_unbiased(seed: int) -> Callable[..., Paired]:
    """Run `engine(s)` and `hand(s)` on the same seed `s`, `pairs` times, and assert the mean
    gap is within k standard errors of zero.

    Pairing on the seed is what cancels the draw both sides share — with the keyed draw of
    §4.6, the same seed faces the same draw — so what is left is bias plus the residual each
    side has alone. The pair seeds derive from the test's seed.

    The reading is in standard errors, as §6 reports it, but with the spread estimated from
    the pairs themselves it follows a Student t with `pairs − 1` degrees of freedom, not a
    normal: at 8 pairs a correct path reads past k=3 2.0% of the time and past k=4 0.5%.
    Choose k for the pairs you run.
    """

    def check(
        engine: Callable[[int], float],
        hand: Callable[[int], float],
        *,
        pairs: int,
        k: float,
    ) -> Paired:
        if pairs < 2:
            raise ValueError(
                f"pairs={pairs}: one pair cannot separate bias from noise — "
                "there is no spread to measure the noise with"
            )
        seeds = [int(s) for s in np.random.SeedSequence(seed).generate_state(pairs)]
        gaps = np.array([engine(s) - hand(s) for s in seeds], dtype=float)
        mean = float(gaps.mean())
        se = float(gaps.std(ddof=1)) / math.sqrt(pairs)
        if se == 0.0:
            assert mean == 0.0, (
                f"bias {mean!r} with zero spread: all {pairs} pairs disagree by the same amount"
            )
            return Paired(mean, se, 0.0, pairs)
        z = mean / se
        assert abs(z) <= k, (
            f"bias {mean:.3g} is {abs(z):.2f} sd from zero, allowed k={k} "
            f"over {pairs} pairs (se {se:.3g})"
        )
        return Paired(mean, se, z, pairs)

    return check


# ── The global stream ────────────────────────────────────────────────────


def _global_stream() -> tuple:
    kind, keys, pos, has_gauss, cached = np.random.get_state()
    return kind, keys.tobytes(), pos, has_gauss, cached


@contextmanager
def _no_global_draws() -> Iterator[None]:
    before = _global_stream()
    yield
    if _global_stream() != before:
        raise AssertionError(
            "the global np.random stream moved: something drew from it or reseeded it. "
            "Draw from the `rng` fixture, or key the draw to the study's seed."
        )


@pytest.fixture
def no_global_draws() -> Callable[[], AbstractContextManager[None]]:
    """A context manager that fails if the block draws from, or reseeds, the global stream."""
    return _no_global_draws


@pytest.fixture(autouse=True)
def _engine_tests_stay_off_the_global_stream(request: pytest.FixtureRequest) -> Iterator[None]:
    """Under `tests/engine/`, every test — its function-scoped fixtures included — runs inside
    `no_global_draws`, and errors at teardown if the stream moved. The old suite outside it
    still draws globally (`stages.py`, `simulation.py`) and dies at the contraction."""
    if not request.node.path.is_relative_to(ENGINE_TESTS):
        yield
        return
    with _no_global_draws():
        yield
