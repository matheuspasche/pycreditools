# Ralph loop v3 — the pair loop for the v0.6 map

The v0.6 engine map is implemented headless by a **pair** that argues: one session
implements a ticket, a **separate fresh session audits it cold**, and they go back and
forth until both are satisfied. Only then does the loop push, open the PR against
`release/v0.6`, merge it and close the issue. **There is no human gate** — owner's ruling.

Code: `docker/ralph_loop_v06.sh`, prompts in `docker/prompts/`, service `ralph_v06` in
`docker-compose.yml`, helper tests in `docker/tests/test_ralph_v06.sh`. The v2 loop
(`docker/ralph_loop.sh`, `docs/dev/ralph-loop-runbook.md`) is untouched and still carries
the seven guardrails this one inherits.

## Run / watch / stop

```bash
docker compose --profile v06 up -d --build ralph_v06   # start (detached)
docker compose --profile v06 logs -f ralph_v06         # loop events
bash docker/watch.sh pycreditools-ralph_v06-1          # step-by-step of the current turn
docker compose --profile v06 stop ralph_v06            # pause; `start` to resume
```

The v06 service sits behind a compose **profile**, so a bare `docker compose up` starts
only the old v2 loop and never both at once.

## The shape of one ticket

| step | who | what |
|---|---|---|
| pick | loop | lowest-numbered open `ready-for-agent` issue whose every `## Blocked by` ref is CLOSED; `#156` (the spec umbrella) is never picked |
| branch | loop | `feat/<issue>-<slug>`, cut fresh from `origin/release/v0.6` — CLAUDE.md's one-ticket-one-branch rule |
| criticise | implementer | **before writing code**: are the blockers really closed *and delivered in the tree*, is part of this already built, does a newer card comment override the body, is there an undeclared dependency? A no means `STATUS: WRONG_TICKET` / `STATUS: BLOCKED`, and the loop comments the evidence on the issue |
| implement | implementer | reads `CLAUDE.md`, `CONTEXT.md`, all 17 tickets, the spec sections it names, the card **with its comments**, the map (#111), `docs/adr/`; TDD red→green; commits; never pushes |
| audit | auditor | fresh session, never sees the implementer's session: re-reads the cards, re-runs the gate, **breaks the implementation to prove the tests bite**, re-checks every measured number, grades BLOCKER/MAJOR/MINOR (NITs are forbidden) |
| argue | both | findings go to the implementer verbatim; it fixes or argues back with evidence. Up to `MAX_ROUNDS` (8) rounds |
| verify | loop | after `VERDICT: AGREED` the loop itself runs `pytest tests --ignore=tests/studio -q` + `ruff check src/pycreditools/engine tests/engine`. Baseline on `release/v0.6` at the time of writing: **444 passed, 8 xfailed** |
| land | loop | push, PR against `release/v0.6` (`Closes #N`), comment recording the agreement, merge, close the issue, drop `ready-for-agent`, fast-forward the local base |

`Studio` is out of scope for the whole map (ticket 13 owns its suite), which is why the
gate ignores `tests/studio`.

## Why the loop owns the outward half

The agents never touch branch state, the PR, the labels or the merge. A turn that dies
half-way can therefore never leave the tracker lying about what shipped — the same
division of labour the v2 loop settled on, for the same reason.

## Configuration

Set in the `ralph_v06` service (or `.env`, which the service reads first):

| var | default | meaning |
|---|---|---|
| `CLAUDE_MODEL` | `claude-opus-5` | model for both roles |
| `CLAUDE_EFFORT` | `medium` | `--effort` for both roles |
| `MAX_ROUNDS` | `8` | audit rounds per ticket before stopping for a human |
| `CONTEXT_CAP_TOKENS` | `450000` | per-session ceiling; over it, that role's next turn starts fresh |
| `BASE_BRANCH` | `release/v0.6` | integration branch and PR base |
| `QUEUE_LABEL` | `ready-for-agent` | the queue |
| `SKIP_ISSUES` | — | space-separated issue numbers to leave alone |
| `MERGE_METHOD` | `--merge` | `--squash` / `--rebase` also accepted |
| `RATE_LIMIT_BACKOFF_SECONDS` | `1800` | fallback only, when the reset hint is unparseable |

## The 450k context ceiling, measured honestly

The cap is enforced on the **live context of each session**, read from the session
transcript: the last assistant message's own request (`input + cache_creation +
cache_read`) plus what it wrote. The result JSON's `usage` block cannot be used for this —
it **aggregates every turn**, so it reports 400k+ of `cache_read` while the real context
sits near 100k.

Two things follow, and the second is the honest caveat:

- Over the cap, the loop clears that role's session id, so its next turn starts **fresh**.
  Nothing is lost: the work lives in commits on the branch, and both prompts are written
  to be re-enterable from scratch (the auditor re-derives everything from the diff anyway).
- Opus 5's context window is **200k**, and Claude Code compacts before it fills. So in
  normal operation neither session can reach 450k, and the ceiling is a **tripwire**, not a
  throttle: it fires only if compaction is off or a longer-window model is configured. If
  you want a real per-ticket spend limit, `MAX_ROUNDS` is the lever that binds.

## Rate limits: retry is resume, not restart

On a 429 the loop parses the reset hint out of the CLI result (`"… resets 10:30pm (UTC)"`)
and sleeps until **one minute past** that instant, then **resumes the same conversation**
(`--resume <session_id>`), so nothing is re-read and no work is repeated. Unparseable
wording falls back to `RATE_LIMIT_BACKOFF_SECONDS`. Detection prefers the structured
`api_error_status` over grepping for `429`, which used to match digits inside token counts.

`docker/tests/test_ralph_v06.sh` pins all of it: the same-day reset, the reset that rolls
to tomorrow, the reset already past (never a negative sleep), the >6h clamp, the fallback,
and the "429 inside a token count is not a rate limit" case.

## Notifications (ntfy)

`docker/notify.sh` posts to `https://ntfy.sh/$NTFY_TOPIC`. The topic is the only secret —
anyone who knows it can read the messages, so keep it in `.env` and out of commits.

On the phone: install **ntfy** (Play Store / App Store / F-Droid), *Subscribe to topic*,
type the topic exactly as in `.env`, leave the server as `ntfy.sh`. Verify end to end from
the host with

```bash
curl -H "Title: teste" -d "chegou?" "https://ntfy.sh/$NTFY_TOPIC"
```

The loop notifies on: start, each ticket landed, a session rotated for context, a rate-limit
sleep, and every stop — wrong ticket, blocked, deadlock (`ESCALATE`), no agreement in
`MAX_ROUNDS`, failed verification, failed push, failed merge, queue blocked, queue empty.

**Env is fixed at container create** (v2 guardrail #4): after editing `.env`, run
`docker compose --profile v06 up -d --force-recreate ralph_v06`, and check inside with
`docker compose --profile v06 exec ralph_v06 sh -c 'echo $NTFY_TOPIC'`.

## Where the loop stops, and what to do

| stop | what it means | recovery |
|---|---|---|
| `STATUS: WRONG_TICKET` | the implementer argues this is not the right work now, with evidence | read the issue comment it left; re-scope or close the card, then restart the loop |
| `STATUS: BLOCKED` | real ambiguity or a missing dependency | decide in the card (the comments are where resolutions live), then restart |
| `VERDICT: ESCALATE` | the pair deadlocked on a design judgement the cards do not settle | both positions are on the issue; rule, and record the ruling in the card or an ADR |
| no agreement in `MAX_ROUNDS` | the argument did not converge | the branch is preserved locally and **not** pushed; the last findings are on the issue |
| verification failed | the pair agreed but the loop's own gate went red | `.ralph/logs/v06/verify_<issue>.log`; nothing was pushed |
| push / merge failed | usually a protected branch or a conflict | fix by hand, then restart the loop |
| queue blocked / empty | nothing actionable left | check the `Blocked by` graph, or review `release/v0.6` |

Logs: `.ralph/logs/v06/<ts>_<role>_<issue>.json` (one per turn, with `.stderr` beside it)
and `verify_<issue>.log`.

## Tests for the loop itself

```bash
docker compose --profile v06 run --rm --entrypoint bash ralph_v06 docker/tests/test_ralph_v06.sh
```

The script sources the loop with `RALPH_V06_LIB_ONLY=1`, which defines the functions and
runs nothing else.
