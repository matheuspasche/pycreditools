"""One signature-driven mechanism, three consumers: `replace`, `to_dict`, `from_dict`.

DoD 2 of the v0.6 spec (§6) asks for *a generic swap-one-field mechanism driven by the
constructor's signature*, and says out loud that if the answer is "the caller passes every
field", the hole stays open. The partial-rebuild family failed three times in the old tree
(#94/#99/#103, re-entered through the sweep in #133) because each rebuild site listed the
fields it happened to remember.

Here no caller lists fields. `fields_of(cls)` reads the constructor signature, and all three
consumers walk what it returns:

- `replace(value, **changes)` swaps the named fields and carries every other one through;
- `to_dict(value)` writes every field, tagged with the type;
- `from_dict(data)` reads every field back, strictly — an unknown or a missing key is a hard
  error, never a default filled in behind the reader's back.

`CreditPolicy.filter`, `CreditPolicy.set_stage` and `Study.vary` are *callers* of `replace`,
not parallel implementations of it, and so will be `ranges=` (tickets 8 and 10), which swaps
the literal of an AST node. A field added to any value type is carried by all of them without
a single caller changing. That is what makes a partial rebuild impossible by construction
instead of by discipline.

Deep freeze lives here too, because it is the same walk. `value_type` makes a frozen dataclass
whose `__post_init__` first passes every field through `freeze`: `list` becomes `tuple`,
`dict` becomes `MappingProxyType`, a builder `Expression` becomes the frozen AST, and a Python
callable is refused. A shallow freeze would let `policy.stages[0].expr.right = 500` through —
the facade immutability v0.6 exists to kill (§4.10).

The callable is refused **at the constructor, not at serialization** (§4.3). A rule that
simulates and then fails at export is discovered after the business decision was taken on it.
Refused on the way in, no branch of `to_dict` can degrade, and `from_dict` failing stops being
an expected path and becomes a real bug.

This module is the mechanism, not the serialization units. `export_rules` / `export_study`
decide what each unit carries (the study unit drops `name`, the rules unit drops the premise);
they land in ticket 12, on top of this.
"""

from __future__ import annotations

import dataclasses
import functools
import inspect
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import numpy as np

from ..expressions import Expression

# tag -> class. The tag is the class name, and `from_dict` accepts nothing else.
_REGISTRY: dict[str, type] = {}

# The one tag that is not a value type. Lower case, so it cannot collide with a class name.
_MAPPING = "mapping"

CALLABLE_REFUSED = (
    "a Python callable is not expressible in a declaration: a rule that is not data cannot be "
    "exported, so it is refused here, not at export. Compute the column on the data and "
    "declare over it — col('my_column') — which is the mutate-then-filter move."
)


def value_type(cls: type) -> type:
    """Make `cls` a frozen, deep-frozen, registered value type.

    The class body declares its fields as a dataclass would, and may define its own
    `__post_init__` for validation; it runs after every field has been frozen.
    """
    own_post_init = cls.__dict__.get("__post_init__")

    def __post_init__(self: Any) -> None:
        for name in fields_of(type(self)):
            set_field(self, name, freeze(getattr(self, name)))
        if own_post_init is not None:
            own_post_init(self)

    cls.__post_init__ = __post_init__  # type: ignore[attr-defined]
    cls = dataclasses.dataclass(frozen=True)(cls)

    # The signature is the source; the dataclass fields must be exactly it. An `InitVar`, a
    # hand-written `__init__` or a non-init field would open a gap between what the
    # constructor takes and what `replace` can read back — the gap this module closes.
    declared = fields_of(cls)
    stored = tuple(f.name for f in dataclasses.fields(cls) if f.init)
    if declared != stored:
        raise TypeError(
            f"{cls.__name__}: constructor parameters {declared} differ from its fields "
            f"{stored}; a value type is its signature, field for field."
        )
    if "type" in declared:
        raise TypeError(f"{cls.__name__}: 'type' is the serialization tag, not a field name.")
    if cls.__name__ in _REGISTRY:
        raise TypeError(f"a value type named {cls.__name__!r} is already registered.")
    _REGISTRY[cls.__name__] = cls
    return cls


@functools.cache
def fields_of(cls: type) -> tuple[str, ...]:
    """The constructor's parameter names, in order — the one list all three consumers read."""
    return tuple(inspect.signature(cls).parameters)


def is_value(obj: Any) -> bool:
    return _REGISTRY.get(type(obj).__name__) is type(obj)


def set_field(obj: Any, name: str, value: Any) -> None:
    """Normalize a field of a frozen value from inside its own `__post_init__`."""
    object.__setattr__(obj, name, value)


def freeze(value: Any) -> Any:
    """Deep-freeze a field value, or refuse it."""
    if is_value(value):
        return value
    if isinstance(value, Expression):
        from ._nodes import from_builder  # the AST is a value type defined on top of this one

        return from_builder(value)
    if isinstance(value, np.generic):
        value = value.item()
    elif isinstance(value, np.ndarray):
        value = value.tolist()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, Mapping):
        return MappingProxyType({_key(k): freeze(v) for k, v in value.items()})
    if callable(value):
        raise TypeError(CALLABLE_REFUSED)
    raise TypeError(
        f"{type(value).__name__} is not a declarable value. A declaration holds literals "
        "(int, float, bool, str), expressions, and tuples or mappings of them."
    )


def _key(key: Any) -> str:
    if not isinstance(key, str):
        raise TypeError(f"mapping keys in a declaration are strings, got {key!r}")
    return key


def replace(value: Any, /, **changes: Any) -> Any:
    """A copy of `value` with `changes` applied and every other field carried through."""
    if not is_value(value):
        raise TypeError(f"{type(value).__name__} is not a value type")
    cls = type(value)
    names = fields_of(cls)
    unknown = sorted(set(changes) - set(names))
    if unknown:
        raise TypeError(f"{cls.__name__} has no field {unknown}; its fields are {list(names)}")
    kwargs = {name: getattr(value, name) for name in names}
    kwargs.update(changes)
    return cls(**kwargs)


def to_dict(value: Any) -> dict[str, Any]:
    """Every field of `value`, tagged with its type. JSON-safe."""
    if not is_value(value):
        raise TypeError(f"{type(value).__name__} is not a value type")
    out: dict[str, Any] = {"type": type(value).__name__}
    for name in fields_of(type(value)):
        out[name] = _encode(getattr(value, name))
    return out


def _encode(value: Any) -> Any:
    if is_value(value):
        return to_dict(value)
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, Mapping):
        return {"type": _MAPPING, "items": {k: _encode(v) for k, v in value.items()}}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    # `freeze` refuses everything else on the way in, so reaching here is a bug, not a path.
    raise TypeError(f"{type(value).__name__} got past freeze(); this is a bug")


def from_dict(data: Mapping[str, Any]) -> Any:
    """The value `to_dict` wrote. Strict: the keys must be exactly the constructor's."""
    if not isinstance(data, Mapping) or "type" not in data:
        raise ValueError(f"not a serialized value (no 'type' tag): {data!r}")
    tag = data["type"]
    cls = _REGISTRY.get(tag) if isinstance(tag, str) else None
    if cls is None:
        raise ValueError(f"unknown value type {tag!r}; known: {sorted(_REGISTRY)}")
    names = fields_of(cls)
    given = set(data) - {"type"}
    missing = [name for name in names if name not in given]
    unknown = sorted(given - set(names))
    if missing or unknown:
        raise ValueError(
            f"{tag}: the serialized fields must be exactly {list(names)}; "
            f"missing {missing}, unknown {unknown}"
        )
    return cls(**{name: _decode(data[name]) for name in names})


def _decode(value: Any) -> Any:
    if isinstance(value, Mapping):
        if value.get("type") == _MAPPING:
            if set(value) != {"type", "items"} or not isinstance(value["items"], Mapping):
                raise ValueError(f"malformed serialized mapping: {value!r}")
            return {k: _decode(v) for k, v in value["items"].items()}
        return from_dict(value)
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value
