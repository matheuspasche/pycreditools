# ADR 0015 — The frozen tree is the tree; evaluating it is a free function

- **Status:** Accepted
- **Date:** 2026-09-10
- **Scope:** the v0.6 AST — `engine/_nodes.py` — the builder the user writes with —
  `expressions.py` — and where a node meets a frame. Excludes what a stage does with the
  evaluated series (ticket 5, §4.2 `apply(df, ctx)`).
- **Tickets:** #177 (this ADR), #178 (this ADR). Consumes #120, #135, #152, #161.
- **Amends:** the living engine spec, §4.3 — *"`expressions.py` já tem a árvore"* and the
  `__repr__` row that calls it *"companheiro do `serialize_expression`"*.
- **Measured against:** `release/v0.6` (`b884b95`).

## Context

Two closed cards met for the first time in ticket 4. **#120** decided that every value type is a
frozen dataclass *"folhas inclusive"*; its measured list was the `Stage`s, the stress classes
and `GroupingRecipe` — **`Expression` was not on it**. **#135** measured the obstacle —
`Expression.__eq__` returns an `Expression` (`expressions.py:31`), so builder nodes can be
neither frozen nor compared by value — and was ruled out of scope because *"#120 decidiu a
matéria sem esperar a pesquisa"* (`docs/research/functional-core.md:317-318`).

The spec inherited both without reconciling them: §4.10 freezes to the leaf, §4.3 says the AST
*is* the tree of `expressions.py`. Ticket 4 (#161, PR #176) resolved the collision on its own:
a frozen mirror in `engine/_nodes.py` (`ColumnNode`, `BinaryNode`, `UnaryNode`, 189 lines),
converted from the builder at the constructor by `from_builder`, carrying `columns()`,
`pretty()` and a round-tripping `repr` — and **no evaluation**. Ticket 5 needs one.

The survival census of `expressions.py` (282 lines) after ticket 16:

- `CalibratedExpression` is built at `expressions.py:72`, `stages.py:329`, `stages.py:426` and
  `deserialize_expression:280`; the first three die in 16, after which no surviving code builds
  it — its only live consumer is `from_builder`, which exists to **refuse** it.
- `serialize_expression`/`deserialize_expression` have non-test callers only in `stages.py` and
  `deployment.py`, all dying in 16. The engine serializes through `engine/_value.py`
  (`to_dict`/`from_dict`, driven by the signature). **Two serializers for one tree.**
- `BinaryExpr.eval` is a 12-branch `if/elif` (`:101-130`) redoing Python's operators.

## Decision 1 — evaluation is a free function inside the engine (#177)

A node is evaluated by a free function internal to `engine/` — `evaluate(node, df) -> Series`,
name to be fixed by ticket 5 — dispatching over the three node types, with the operator symbol
mapped to Python's `operator` functions instead of a branch per symbol. The node stays pure,
serializable data; `_nodes.py` does not import pandas.

**Why.** The spine of #152's resolution (owner) reads *"Método declara, função livre calcula.
**Nenhum método toca a base.**"* `node.eval(df)` would be exactly a method touching the base.
The methods the node already has — `columns()`, `pretty()` — touch no data and fit the rule.
And §5 lists the `ctx`, the one-member `Protocol` and re-keying on the AST as **internal**,
exercised only through seam 1: the evaluator is one more of those.

**Rejected:**

- *Public method on the node.* Needs a declared amendment to the spine, and hands the user a
  calculation path outside `simulate` — no bind, no column check.
- *Private method on the node.* Keeps per-class locality without breaking the spine's letter,
  but couples the value type (§4.10) to the engine (§4.6), which the spec keeps apart. Three
  closed node types (§4.3) make the dispatch cheap.

## Decision 2 — the frozen tree is canonical; the builder becomes write-sugar (#178)

At the contraction (ticket 16), `expressions.py` keeps `col()`, the 14 operator dunders and three
plain node classes whose only job is to be converted. It loses `eval` on every node,
`get_columns`, `CalibratedExpression` and `serialize_expression`/`deserialize_expression` —
about 140 of its 282 lines. `from_builder` is the permanent conversion, and `to_dict` is the
only serializer of the tree.

**Why.** It keeps the idiom users write — `col("segment") == "A"` — working, and keeps value
equality on the frozen side, which is tested contract (10 value-equality asserts in
`tests/engine/`, among them `eval(repr(policy), …) == policy`). With Decision 1 in place,
keeping the builder whole would leave **two evaluators** of the same tree besides two
serializers.

**Rejected:**

- *One tree* — `col()` builds frozen nodes and `==` becomes structural, with `.eq()`/`.ne()` for
  building. Measured trap, simulated on a frozen dataclass: `col("segment") == "A"` returns
  `False` silently, `!=` returns `True`, and `(col("segment") == "A") & (col("x") > 2)` builds
  `False & col("x")` — which today's `BinaryNode` **accepts**, since `bool` is a legal literal
  in `&` (`_nodes.py:95-100`). Closing it needs a new guard and rewrites 18 `==` and 2 `!=`
  sites (README 1, docs 3, tests 14).
- *Two full trees* — the status quo after #161. Zero work in 16, and two serializers plus two
  evaluators for the life of the package.

## Consequences

- **Ticket 5 (#162)** writes the evaluator as an engine internal, tested only through `simulate`.
- **Ticket 16 (#172)** gains an explicit item: `expressions.py` does not survive intact. Today its
  checklist names only `CalibratedExpression`.
- **§4.3** is amended to say the AST is the frozen tree and the builder is sugar the constructor
  converts; the `repr` row points at `to_dict`, not `serialize_expression`.
- Deep freeze (#120) is untouched — this ADR decides which tree is frozen, not whether.
