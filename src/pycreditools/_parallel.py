from collections.abc import Callable, Iterable
from typing import Any


def parallel_map(
    fn: Callable[[Any], Any],
    items: Iterable[Any],
    parallel: bool = False,
    n_workers: int | None = None,
    desc: str | None = None,
) -> list[Any]:
    """Map fn over items, optionally in parallel via concurrent.futures."""
    if not parallel:
        return [fn(item) for item in items]

    import concurrent.futures

    with concurrent.futures.ProcessPoolExecutor(max_workers=n_workers) as executor:
        results = list(executor.map(fn, items))

    return results
