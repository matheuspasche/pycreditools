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
| `CONTEXT_CAP_TOKENS` | `250000` | per-session ceiling; over it, that role's next turn starts fresh |
| `CROSS_TALK_CHARS` | `12000` | cap on the report/findings text pasted verbatim into the other role's prompt (the tail is kept) |
| `BASE_BRANCH` | `release/v0.6` | integration branch and PR base |
| `QUEUE_LABEL` | `ready-for-agent` | the queue |
| `SKIP_ISSUES` | — | space-separated issue numbers to leave alone |
| `MERGE_METHOD` | `--merge` | `--squash` / `--rebase` also accepted |
| `RATE_LIMIT_BACKOFF_SECONDS` | `1800` | fallback only, when the reset hint is unparseable |
| `WORK_WINDOW_START` / `_END` / `_TZ` | `22:00` / `08:00` / `America/Sao_Paulo` | the loop only works inside this window |
| `WEEKLY_BUDGET_USD` / `BUDGET_STOP_PCT` | `150` / `80` | usage meter ceiling over a rolling 7 days |
| `NTFY_PRIORITY_ALERT` / `_INFO` | `default` / `low` | nothing is ever sent as `urgent` |
| `HEARTBEAT_SECONDS` | `7200` | sign of life during any long wait |
| `TURN_TIMEOUT_SECONDS` | `7200` | watchdog: kills a hung turn |
| `VENV` | `/home/ralph/venv` | the gate's virtualenv, built inside the container |

**Edit these in `.env`, not here.** `environment:` in compose **wins** over `env_file`, so a
knob pinned in `docker-compose.yml` makes the `.env` entry decorative. Only the things that
identify the map (branch, queue label, parent issue, model, skip list) stay in compose; the
policy knobs live in `.env`, which the loop never touches and you can edit while it runs.
See `.env.example`.

## The work window

The loop works only between `WORK_WINDOW_START` and `WORK_WINDOW_END` (owner's hours: the
machine is his during the day). The window is checked **between turns, never inside one** —
interrupting a turn would lose whatever has not become a commit yet. Outside it the loop
sleeps and says so once, then heartbeats.

A window that does not suspend the host is a window that does not exist: a suspended
machine runs nothing, and a suspend in the middle of a turn kills the API call in flight.
`scripts/ralph_awake.sh` holds a `systemd-inhibit` lock **only while the window is open**,
so the machine still sleeps normally during the day. Run it on the host, in a terminal you
leave open.

## The usage meter, and why it is not money

The account runs on a **subscription**, so nothing here is billed — what the loop spends is
**quota**. But quota is not exposed by any API, and the only consumption figure observable
locally is `total_cost_usd`, which the CLI reports per turn: what those tokens *would* cost
on the API. It is a **meter, not an invoice**, and it works as a brake because it rises with
the quota consumed.

Each turn appends `<epoch>\t<meter>` to `.ralph/usage.tsv`. When the rolling 7-day sum
reaches `BUDGET_STOP_PCT` of `WEEKLY_BUDGET_USD`, the loop **sleeps** (it does not die) and
rechecks hourly — a rolling window recovers on its own as old turns age out. Calibrate the
ceiling by comparing that file's running total against the percentage `/usage` reports in an
interactive session. Measured reference: one implementer turn on ticket 1 marked **11.10**.

## Nothing is urgent

`urgent` on ntfy rings like an alarm and once woke the owner at 4am. This is a personal
project running overnight and nothing in it is time-critical, so the ceiling is `default`
(`NTFY_PRIORITY_ALERT`) and routine progress goes out at `low` (`NTFY_PRIORITY_INFO`).

The counterpart is the **heartbeat**: from a phone, silence and death look identical, and
that ambiguity once hid 8 hours of a wedged loop. Any long wait — quota, closed window,
usage ceiling — emits a low-priority sign of life every `HEARTBEAT_SECONDS` saying what it
is waiting for and when it expects to resume.

## The gate's virtualenv is the container's, never the host's

`verify_turn` and both prompts use `$VENV` (`/home/ralph/venv`, a named volume built once by
the entrypoint). It must **not** be the tree's `.venv-linux`: that one is built by the host
interpreter (3.14 on Fedora) and its `site-packages` is unreadable to the container's 3.11,
so `pytest` died with `ModuleNotFoundError` on every ticket and the loop would have refused
even correct work.

## The 150k context ceiling: rotate rather than compact

The cap is enforced on the **live context of each session**, read from the session
transcript: the last assistant message's own request (`input + cache_creation +
cache_read`) plus what it wrote. The result JSON's `usage` block cannot be used for this —
it **aggregates every turn**, so it reports 400k+ of `cache_read` while the real context
sits near 100k.

Two things follow, and the second is the honest caveat:

- Over the cap, the loop clears that role's session id, so its next turn starts **fresh**.
  Nothing is lost: the work lives in commits on the branch, and both prompts are written
  to be re-enterable from scratch (the auditor re-derives everything from the diff anyway).
- **Measured 2026-09-13:** an implementer turn on ticket 1 reached **272k** of live
  context, so the window is larger than the 200k this runbook once assumed and the old cap
  would still not have fired. The rotation notice is a `low` ntfy, not a problem.
- The cap was **450k** and therefore inert: Opus 5's window is **200k** and Claude Code
  compacts before it fills, so no session could ever reach the tripwire. Set **below** the
  window it becomes the lever it was meant to be — the session rotates fresh instead of
  being compacted. That is the cheaper of the two: compaction pays a summarisation turn and
  then keeps paying for a lossy summary, while a rotation re-reads the ticket (a few
  thousand tokens) against a tree the commits already describe. `MAX_ROUNDS` still binds
  the per-ticket ceiling.

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
