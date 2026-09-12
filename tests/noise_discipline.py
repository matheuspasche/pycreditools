"""Noise discipline for tests that compare an engine number with a number computed by hand.

§6 "Higiene de semente — pré-requisito, não higiene" (ticket 2, #158). Such a test declares
three things, or it is a flake:

1. **Seed policy** — seeds are derived (`derive_seed`, `derive_seeds`), never taken from a
   global `np.random.seed`. `--seed-offset N` moves every derived seed at once, so a test that
   passes on one realization only is one command away from being caught.
2. **Tolerance in units of noise** — `assert_within_k_sd`: the band is an sd measured
   (`measure_sd`) at a declared n and scaled by 1/√n to the n under test. Never p.p. absolute.
3. **Rounds where the criterion is bias** — `assert_unbiased`, with the pairing declared. One
   round against one round does not separate bias from noise: #149 read 4.1 sd on a correct
   path, and 8 rounds against 8 hand simulations (0.2 / 1.2 / 0.9 standard errors) cleared it.

Plus what "exact" means for a float (`assert_exact`), what "reproduces under the seed" means
(`assert_reproducible`), and the two guards of §4.6 — "Nenhum np.random global sobra no
núcleo": `no_global_draws` at run time, `find_unkeyed_draws` over source.

Plain functions, importable from any test (`pythonpath = ["tests"]` in `pyproject.toml`) and,
with `tests/` put on `sys.path`, from a script outside pytest such as `validation/`;
`tests/conftest.py` wraps the seed policy in fixtures.
"""

from __future__ import annotations

import ast
import math
import numbers
import random
import zlib
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

EPS = float(np.finfo(float).eps)
MAX_FALSE_ALARM = 0.01
MIN_SD_SEEDS = 20


def _integer(name: str, value: Any, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < minimum:
        raise ValueError(f"{name}={value!r}: an integer >= {minimum}")
    return int(value)


def _positive(name: str, value: Any) -> Any:
    if (
        isinstance(value, bool)
        or not isinstance(value, numbers.Real)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name}={value!r}: a finite number > 0")
    return value


def _sd(values: np.ndarray) -> float:
    """The sample sd (ddof=1), and exactly 0 when every value is the same — `np.std` of equal
    values reads ~1e-18 off a mean that rounds, which would pass for spread."""
    return 0.0 if bool(np.all(values == values[0])) else float(values.std(ddof=1))


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value):
        raise ValueError(f"{name}={value!r}: a finite number")
    return float(value)


# ── 1. Seeds are derived ─────────────────────────────────────────────────


def derive_seed(key: str, *, offset: int = 0) -> int:
    """A seed from a key — a test's node id, a module's, a study's name.

    CRC-32 of the key: stable across runs, machines and Python versions (unlike `hash`), and a
    plain non-negative int below 2**32 — a valid `Study.seed`. Offset 0 is the suite's own
    realization; any other offset is another one, for every key at once.
    """
    offset = _integer("offset", offset, minimum=0)
    return zlib.crc32((key if offset == 0 else f"{offset}:{key}").encode())


def derive_seeds(key: str, count: int, *, offset: int = 0) -> list[int]:
    """`count` distinct plain-int seeds from one key — the rounds of `measure_sd` and
    `assert_unbiased`."""
    count = _integer("count", count, minimum=1)
    return _distinct(np.random.SeedSequence(derive_seed(key, offset=offset)), count, exclude=())


def _distinct(sequence: np.random.SeedSequence, count: int, *, exclude: Sequence[int]) -> list[int]:
    taken, seeds = set(exclude), []
    for value in sequence.generate_state(2 * count + len(taken)):
        if int(value) not in taken:
            taken.add(int(value))
            seeds.append(int(value))
        if len(seeds) == count:
            return seeds
    raise RuntimeError(f"could not derive {count} distinct seeds")  # 32-bit collisions only


# ── Exact, for a float ───────────────────────────────────────────────────


def float_floor(observed: float, expected: float, *, terms: int) -> float:
    """The rounding a float that sums `terms` terms can carry: 2·terms·ε·max(|x|).

    Higham's bound for recursive summation of terms of one sign — sums, and ratios of sums,
    which is what a rate is; running totals (`cumsum`, the mechanism of ticket 10) sit inside
    it and pairwise sums far inside. It does not cover cancellation: `(1e8 + 0.1) - 1e8`
    against `0.1` carries far more than this. It is machine rounding, not a tolerance: at 3 MM
    terms it is 1.3e-9 relative, orders of magnitude below any sd §6 measures.
    """
    terms = _integer("terms", terms, minimum=1)
    return 2 * terms * EPS * max(abs(observed), abs(expected))


def assert_exact(observed: float, expected: float, *, terms: int) -> None:
    """Equal up to machine rounding — the hard invariants of §6 and the exactness tests of
    tickets 8 and 10. `terms` is the number of terms summed into the number; no default."""
    o, e = _finite("observed", observed), _finite("expected", expected)
    floor = float_floor(o, e, terms=terms)
    assert abs(o - e) <= floor, (
        f"{o!r} vs {e!r}: gap {abs(o - e):.3g} exceeds the rounding of {terms} terms ({floor:.3g})"
    )


# ── 2. Tolerance in units of noise ───────────────────────────────────────


def measure_sd(fn: Callable[[int], float], *, seeds: Sequence[int]) -> float:
    """The sd of `fn(seed)` over `seeds` (ddof=1) — the band `assert_within_k_sd` scales.

    At least 20 seeds: the sd's own relative error is 1/√(2(m−1)) — 16% at 20 — and an sd
    read low shrinks every k built on it. A number with no spread is refused: it does not
    draw, so compare it with `assert_exact`.
    """
    seeds = list(seeds)
    if len(seeds) < MIN_SD_SEEDS:
        raise ValueError(
            f"{len(seeds)} seeds: measure_sd needs at least {MIN_SD_SEEDS} — the sd of an sd "
            "read from fewer is too wide to build a band on"
        )
    values = np.array([_finite("fn(seed)", fn(s)) for s in seeds])
    sd = _sd(values)
    if sd == 0.0:
        raise ValueError("fn has no spread over the seeds: it does not draw — use assert_exact")
    return sd


def assert_within_k_sd(
    observed: float, expected: float, *, sd: float, at_n: int, n: int, k: float
) -> None:
    """`observed` is within k standard errors of `expected`, the standard error being `sd`
    scaled from `at_n` rows to `n` rows: sd·√(at_n / n).

    `sd` is the sd of the compared quantity measured at `at_n` rows (`measure_sd`) — the sd of
    the gap when both sides draw. That is §6's own form, "O sd medido a 3 MM … escala com
    1/√n": a band measured at 3 MM and scaled holds at 200k, where an absolute tolerance
    chosen at 3 MM fails on its own. `at_n` and `n` count the same unit. An analytic per-row sd
    is the case at_n=1, honest only when every row draws alike — which a book whose keep-ins
    are observed does not. No argument has a default.
    """
    o, e = _finite("observed", observed), _finite("expected", expected)
    sd, k = _positive("sd", sd), _positive("k", k)
    at_n, n = _integer("at_n", at_n, minimum=1), _integer("n", n, minimum=1)
    se = sd * math.sqrt(at_n / n)
    z = (o - e) / se
    assert abs(z) <= k, (
        f"{o!r} vs {e!r}: {abs(z):.2f} sd apart, allowed k={k} at n={n} "
        f"(sd {sd:.3g} measured at n={at_n}, se {se:.3g})"
    )


# ── 3. Rounds where the criterion is bias ────────────────────────────────


def t_two_sided_tail(k: float, df: int) -> float:
    """P(|T| > k) for Student's t with `df` degrees of freedom — the closed form for integer
    df (Abramowitz & Stegun 26.7.3–4), so no scipy."""
    k, df = _positive("k", k), _integer("df", df, minimum=1)
    theta = math.atan(k / math.sqrt(df))
    cos2 = math.cos(theta) ** 2
    if df % 2 == 1:
        acc = 0.0
        if df > 1:
            term = acc = math.cos(theta)
            for j in range(3, df - 1, 2):
                term *= cos2 * (j - 1) / j
                acc += term
        inside = 2 / math.pi * (theta + math.sin(theta) * acc)
    else:
        term = acc = 1.0
        for j in range(2, df - 1, 2):
            term *= cos2 * (j - 1) / j
            acc += term
        inside = math.sin(theta) * acc
    return max(0.0, 1.0 - inside)


@dataclass(frozen=True)
class BiasReading:
    """What `assert_unbiased` read: the mean gap engine − hand, its standard error, the gap in
    standard errors, the rounds, the pairing, and how often a correct path would read past k
    at these rounds."""

    gap: float
    se: float
    z: float
    rounds: int
    paired: bool
    false_alarm: float


def assert_unbiased(
    engine: Callable[[int], float],
    hand: Callable[[int], float],
    *,
    seeds: Sequence[int],
    k: float,
    paired: bool,
    terms: int,
) -> BiasReading:
    """Engine and hand agree on average, read in standard errors over `len(seeds)` rounds.

    The pairing is declared, with no default, because it decides where the power comes from:

    - `paired=False` — the #149 method, and the one DoD 3 ("referência calculada fora do
      motor") is always safe with. The engine runs on `seeds`, the hand on as many seeds
      derived from them and disjoint from them; se = √(s_e²/m + s_h²/m) (Welch).
    - `paired=True` — engine and hand run on the same seed and the gaps are read; se =
      sd(gaps)/√m. Honest only when the hand side consumes the engine's draw *primitive* — the
      keyed draw of §4.6, which "torna o pareamento barato" — and never a result of the
      engine. With unshared draws pairing buys nothing.

    k is declared too, and refused when a correct path would read past it more than 1% of the
    time: the reading is a Student t with m−1 degrees of freedom (the worst case of Welch's),
    so at 8 rounds k=3 errs 2.0% and k=4 0.5%, and at 2 rounds no usable k passes. Gaps within
    the rounding of `terms` summed terms (`float_floor`) count as exact zeros, so an exact
    path never reads as bias.
    """
    seeds = [_integer("seed", s, minimum=0) for s in seeds]
    m = len(seeds)
    if m < 2:
        raise ValueError(f"{m} round(s): one round cannot separate bias from noise")
    if len(set(seeds)) != m:
        raise ValueError("seeds repeat: every round is its own realization")
    k = _positive("k", k)
    if not isinstance(paired, bool):
        raise TypeError(f"paired= is declared True or False, got {paired!r}")
    false_alarm = t_two_sided_tail(k, m - 1)
    if false_alarm > MAX_FALSE_ALARM:
        raise ValueError(
            f"k={k} over {m} rounds: a correct path reads past it {false_alarm:.1%} of the time "
            f"(Student t, {m - 1} df), above {MAX_FALSE_ALARM:.0%} — raise k or the rounds"
        )
    engine_values = np.array([_finite("engine(seed)", engine(s)) for s in seeds])
    hand_seeds = seeds if paired else _distinct(np.random.SeedSequence(seeds), m, exclude=seeds)
    hand_values = np.array([_finite("hand(seed)", hand(s)) for s in hand_seeds])
    if paired:
        gaps = engine_values - hand_values
        floors = [float_floor(e, h, terms=terms) for e, h in zip(engine_values, hand_values)]
        gaps = np.where(np.abs(gaps) <= floors, 0.0, gaps)
        gap, se = float(gaps.mean()), _sd(gaps) / math.sqrt(m)
    else:
        mean_e, mean_h = float(engine_values.mean()), float(hand_values.mean())
        gap = mean_e - mean_h
        if abs(gap) <= float_floor(mean_e, mean_h, terms=terms):
            gap = 0.0
        se = math.sqrt(_sd(engine_values) ** 2 / m + _sd(hand_values) ** 2 / m)
    if se == 0.0:
        assert gap == 0.0, (
            f"bias {gap!r} with zero spread: every round disagrees by the same amount"
        )
        return BiasReading(gap, se, 0.0, m, paired, false_alarm)
    z = gap / se
    assert abs(z) <= k, (
        f"bias {gap:.3g} is {abs(z):.2f} sd from zero, allowed k={k} over {m} rounds "
        f"({'paired' if paired else 'unpaired'}, se {se:.3g})"
    )
    return BiasReading(gap, se, z, m, paired, false_alarm)


# ── Reproduces under the seed ────────────────────────────────────────────


def assert_reproducible(fn: Callable[[int], Any], seed: int) -> None:
    """`fn(seed)` twice gives the same result, value for value and dtype for dtype — §4.6's
    "reproduz sob semente", for ticket 5 to hold `simulate` to. Equality is numeric: NaN
    matches NaN, and -0.0 matches 0.0."""
    seed = _integer("seed", seed, minimum=0)
    _assert_identical(fn(seed), fn(seed), "fn(seed)")


def _assert_identical(a: Any, b: Any, where: str) -> None:
    if isinstance(a, pd.DataFrame):
        pd.testing.assert_frame_equal(a, b, check_exact=True, obj=where)
    elif isinstance(a, pd.Series):
        pd.testing.assert_series_equal(a, b, check_exact=True, obj=where)
    elif isinstance(a, np.ndarray):
        assert isinstance(b, np.ndarray) and a.dtype == b.dtype, (
            f"{where}: {a.dtype} vs {getattr(b, 'dtype', type(b).__name__)}"
        )
        np.testing.assert_array_equal(a, b, err_msg=where)
    elif isinstance(a, (tuple, list)):
        assert type(a) is type(b) and len(a) == len(b), f"{where}: {a!r} vs {b!r}"
        for i, (x, y) in enumerate(zip(a, b)):
            _assert_identical(x, y, f"{where}[{i}]")
    elif isinstance(a, dict):
        assert type(b) is dict and list(a) == list(b), f"{where}: keys {list(a)} vs {b!r}"
        for key in a:
            _assert_identical(a[key], b[key], f"{where}[{key!r}]")
    else:
        assert type(a) is type(b), f"{where}: {type(a).__name__} vs {type(b).__name__}"
        assert a == b or (a != a and b != b), f"{where}: {a!r} vs {b!r}"


# ── The global streams, at run time ──────────────────────────────────────


def _streams() -> tuple[tuple, tuple]:
    kind, keys, pos, has_gauss, cached = np.random.get_state()
    return (kind, keys.tobytes(), pos, has_gauss, cached), random.getstate()


class StreamWatch:
    """Where the global streams — numpy's legacy one and the stdlib `random` — stood when last
    looked at. `check(where)` raises if either moved since, naming where, and looks again, so
    each move is reported once."""

    def __init__(self) -> None:
        self._state = _streams()

    def check(self, where: str) -> None:
        now = _streams()
        moved = [name for name, b, a in zip(("np.random", "random"), self._state, now) if b != a]
        self._state = now
        if moved:
            raise AssertionError(
                f"the global {' and '.join(moved)} stream moved {where}: something drew from it "
                "or reseeded it. Draw from a Generator on a derived seed, or key the draw to the "
                "study's seed."
            )


@contextmanager
def no_global_draws() -> Iterator[None]:
    """Fails if the block draws from, or reseeds, a global stream."""
    watch = StreamWatch()
    yield
    watch.check("inside the block")


_DEFAULT_RNG = np.random.default_rng


def seeded_default_rng(seed: Any = None) -> np.random.Generator:
    """`np.random.default_rng` that refuses to run without a seed — installed over the real
    one under `tests/engine/`. Without a seed it draws OS entropy: a stream no seed replays."""
    if seed is None:
        raise AssertionError(
            "np.random.default_rng() without a seed draws OS entropy, which no seed replays — "
            "pass a derived seed, or key the draw to the study's seed"
        )
    return _DEFAULT_RNG(seed)


# ── The global streams, in source ────────────────────────────────────────

_KEYED = frozenset(
    {"default_rng", "Generator", "SeedSequence", "BitGenerator"}
    | {"PCG64", "PCG64DXSM", "MT19937", "Philox", "SFC64"}
)


def find_unkeyed_draws(source: str, filename: str = "<source>") -> list[str]:
    """The draws in `source` that no seed replays: stdlib `random`, any global `np.random`
    function or `RandomState`, and a Generator, SeedSequence or bit generator built without a
    seed (or with a literal `None`). Catches names bound at import (`from numpy.random import
    default_rng`), which a run-time patch cannot. Declared holes — it reads names, not values:
    `np.random` or a constructor passed around or aliased (`make = np.random.default_rng`),
    `getattr(np.random, ...)`, and a seed that is `None` only at run time (`def f(seed=None):
    return default_rng(seed)`) — `Study` refusing a non-int seed closes the last for the
    engine's own draws."""
    tree = ast.parse(source, filename)
    numpy_names: set[str] = set()
    random_names: set[str] = set()
    keyed_names: dict[str, str] = {}
    found: list[str] = []

    def flag(node: ast.AST, what: str) -> None:
        found.append(f"{filename}:{node.lineno}: {what}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "random":
                    flag(node, "stdlib random")
                elif alias.name == "numpy":
                    numpy_names.add(alias.asname or "numpy")
                elif alias.name == "numpy.random":
                    if alias.asname:
                        random_names.add(alias.asname)
                    else:
                        numpy_names.add("numpy")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "random":
                flag(node, "stdlib random")
            elif node.module == "numpy":
                random_names.update(a.asname or a.name for a in node.names if a.name == "random")
            elif node.module == "numpy.random":
                for alias in node.names:
                    if alias.name in _KEYED:
                        keyed_names[alias.asname or alias.name] = alias.name
                    else:
                        flag(node, f"global np.random.{alias.name}")

    def numpy_random_attr(expr: ast.AST) -> str | None:
        if not isinstance(expr, ast.Attribute):
            return None
        owner = expr.value
        if isinstance(owner, ast.Name) and owner.id in random_names:
            return expr.attr
        if (
            isinstance(owner, ast.Attribute)
            and owner.attr == "random"
            and isinstance(owner.value, ast.Name)
            and owner.value.id in numpy_names
        ):
            return expr.attr
        return None

    for node in ast.walk(tree):
        attr = numpy_random_attr(node)
        if attr is not None and attr not in _KEYED:
            flag(node, f"global np.random.{attr}")
        if isinstance(node, ast.Call):
            name = numpy_random_attr(node.func)
            if name is None and isinstance(node.func, ast.Name):
                name = keyed_names.get(node.func.id)
            if name in _KEYED:
                given = (
                    node.args[0] if node.args else next((kw.value for kw in node.keywords), None)
                )
                if given is None or (isinstance(given, ast.Constant) and given.value is None):
                    flag(node, f"{name}() without a seed")
    return found
