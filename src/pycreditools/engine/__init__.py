"""The v0.6 engine surface, growing beside the old one.

This package is the *expand* half of a package-level expand–contract. The v0.6
surface is built here, in its own namespace, while `policy.py`, `simulation.py`
and `sweep.py` keep running untouched. Nothing is migrated in place; the old
surface is deleted whole at the contraction, and this one takes its name then.

**This package is deliberately unreachable from the top level until then.**
`import pycreditools` does not bind `pycreditools.engine`, and `engine` is
absent from `pycreditools.__all__`. `tests/test_packaging.py` fails if either
stops being true. The reason is that `.filter` cannot mean two things at once:
`CreditPolicy.filter(self, name, condition)` takes `name` positionally first
(`policy.py:105`), so `.filter(col("age") >= 18)` under today's signature binds
the `Expression` to `name` and dies on the missing `condition`. Widening the
signature does not reconcile them — the two surfaces collide, and the only way
both stay alive through the twelve tickets is for exactly one of them to be
reachable as `pct.`.

The gate is not a style rule. It is what makes a vertical slice possible: each
ticket lands a working piece of the new surface without a single site of the
old one having to move on the same commit. Reaching in from the top before the
contraction reintroduces the collision the separation exists to prevent.

The shared code stays shared rather than copied — `_kernels/`, `expressions.py`
and `sample_data.py` are read from here, not duplicated. The sharing of
`expressions.py` is read-only.

**What is here: the declaration block (ticket 4).** Four types, and the spine in two lines —
the `CreditPolicy` declares what you DECIDE; the `Premise` declares what you ASSUME.
`DataSchema` names the columns the engine reads by role, and `Study` is the encounter of the
three, with the seed. All four are frozen to the leaf and derive through one signature-driven
mechanism (`_value.py`). Nothing here executes yet: `simulate` lands in ticket 5.
"""

from .errors import LabelRequired, PremiseError, SchemaError
from .policy import CreditPolicy
from .premise import Premise
from .schema import DataSchema
from .study import Study

__all__: list[str] = [
    "DataSchema",
    "CreditPolicy",
    "Premise",
    "Study",
    "LabelRequired",
    "PremiseError",
    "SchemaError",
]
