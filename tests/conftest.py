"""The core suite's fixtures and guards; the discipline itself lives in `noise_discipline.py`.

- **Seeds** (§6, ticket 2): `seed` and `rng` for a test, `seeds(count)` for its rounds, and
  `seed_offset` for fixtures of wider scope, which derive their own with `derive_seed` of
  their node id. `--seed-offset N` moves every one of them to another realization, and the
  report header names the offset in use.
- **Guard** (§4.6, "Nenhum np.random global sobra no núcleo"): under `tests/engine/`, every
  test and every module runs with the global streams watched and `np.random.default_rng`
  refusing to run without a seed. The old suite outside it still draws globally
  (`stages.py`, `simulation.py`) and dies at the contraction (ticket 16). Declared hole:
  session-scoped fixtures.

`tests/studio/conftest.py` is the Studio's (ticket 13); this one is the core's.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pytest
from noise_discipline import StreamWatch, derive_seed, derive_seeds, seeded_default_rng

pytest_plugins = ["pytester"]

ENGINE_TESTS = Path(__file__).parent / "engine"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--seed-offset",
        type=int,
        default=0,
        metavar="N",
        help="move every derived seed to another realization (0 is the suite's own)",
    )


def pytest_report_header(config: pytest.Config) -> str:
    return f"seed offset: {config.getoption('--seed-offset')} (tests/noise_discipline.py)"


# ── Seeds ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def seed_offset(pytestconfig: pytest.Config) -> int:
    return pytestconfig.getoption("--seed-offset")


@pytest.fixture
def seed(request: pytest.FixtureRequest, seed_offset: int) -> int:
    """The test's seed: `derive_seed` of its node id, under `--seed-offset`.

    Renaming a test changes its seed. A test that passes on one seed only was testing a
    realization, not the path — rerunning with `--seed-offset` is how that shows.
    """
    return derive_seed(request.node.nodeid, offset=seed_offset)


@pytest.fixture
def seeds(request: pytest.FixtureRequest, seed_offset: int) -> Callable[[int], list[int]]:
    """`seeds(count)` — the test's rounds, for `measure_sd` and `assert_unbiased`."""
    return lambda count: derive_seeds(request.node.nodeid, count, offset=seed_offset)


@pytest.fixture
def rng(seed: int) -> np.random.Generator:
    """A `Generator` on the test's seed. Never the global stream."""
    return np.random.default_rng(seed)


# ── Guard ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _engine_module_watch(request: pytest.FixtureRequest) -> Iterator[StreamWatch | None]:
    """Under `tests/engine/`: `np.random.default_rng` refuses to run without a seed for the
    whole module, and the global streams are watched from its start. Each move is reported
    once, where it happened — a module fixture's at the setup of the first test that sees it,
    a test's at its teardown, a module fixture's teardown at the module's end."""
    if not request.node.path.is_relative_to(ENGINE_TESTS):
        yield None
        return
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(np.random, "default_rng", seeded_default_rng)
        watch = StreamWatch()
        yield watch
        watch.check("in a module-scoped fixture's teardown")


@pytest.fixture(autouse=True)
def _engine_test_watch(_engine_module_watch: StreamWatch | None) -> Iterator[None]:
    if _engine_module_watch is None:
        yield
        return
    _engine_module_watch.check("in a module-scoped fixture, before this test")
    yield
    _engine_module_watch.check("in this test or its function-scoped fixtures")
