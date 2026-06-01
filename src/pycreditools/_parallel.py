import pandas as pd
from typing import Callable, Iterable, Any, Optional

def parallel_map(
    fn: Callable[[Any], Any],
    items: Iterable[Any],
    parallel: bool = False,
    n_workers: Optional[int] = None,
    desc: Optional[str] = None
) -> list[Any]:
    """Map fn over items, optionally in parallel via concurrent.futures."""
    if not parallel:
        return [fn(item) for item in items]
        
    import concurrent.futures
    with concurrent.futures.ProcessPoolExecutor(max_workers=n_workers) as executor:
        results = list(executor.map(fn, items))
        
    return results

def parallel_map_df(
    fn: Callable[[Any], pd.DataFrame],
    items: Iterable[Any],
    parallel: bool = False,
    n_workers: Optional[int] = None,
    desc: Optional[str] = None
) -> pd.DataFrame:
    """Map fn over items and concat results into DataFrame."""
    results = parallel_map(fn, items, parallel, n_workers, desc)
    if not results:
        return pd.DataFrame()
    return pd.concat(results, ignore_index=True)
