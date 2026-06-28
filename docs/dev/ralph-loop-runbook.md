# Ralph loop — runbook & guardrails

The "ralph loop" runs Claude Code headless in Docker to implement the PRD-12 slice
issues, one per turn, on a single `prd-12-studio-v2` branch with one PR. Code:
`docker/ralph_loop.sh`, `docker-compose.yml`. Orientation: `docs/ORIENTATION.md`.

## Run / watch / stop

```bash
docker compose up -d --build      # build + start (detached)
docker compose logs -f            # loop events (issue picked / done / stopped)
bash docker/watch.sh              # live step-by-step of the current turn
docker compose stop               # pause; `start` to resume, `down` to remove
```

The loop stops cleanly (exit 0) for a human when: all slices done, a slice is
BLOCKED/ERROR, a push fails, or verification fails. `restart: on-failure` means a
clean stop stays stopped (only a real crash relaunches).

## What can go wrong, and the guardrail for it

These are the failure modes actually hit while bringing the loop up, and the
mitigations now baked into `docker/ralph_loop.sh` / `docker-compose.yml`.

| # | Failure mode | Symptom | Guardrail |
|---|---|---|---|
| 1 | **Phantom blocker from a title** — the dependency parser grabbed every `#N` on a "Blocked by" line, so a blocker whose *title* contained `#N` (e.g. "Bancada tracer #1") injected a fake blocker (#1, a MERGED PR that never reports CLOSED). | "N todo issue(s) left but all blocked" with deps that are actually satisfied; queue deadlocks. | `blockers_all_closed` parses only the **leading** `^- #N` of each list item, never numbers inside titles. |
| 2 | **Infinite restart cycle** — `restart: unless-stopped` relaunched the container every time the loop cleanly exited "for a human". | Container "Up a few seconds", logs repeat start→stop; ntfy spam. | `restart: on-failure` — exit 0 (clean stop) does not relaunch; only a crash does. |
| 3 | **Trusting `STATUS: DONE` blind** — a turn could report done with red/sham tests and the loop would push + close. | Broken commit on the branch / closed issue with failing tests. | **Verification gate**: after DONE the loop re-runs `pytest tests/studio` (+ ruff) itself; only green → push + close. Red → revert label to `status:todo`, don't push, stop. |
| 4 | **Stale env in a running container** — env vars are fixed at container create, so editing `.env` (e.g. `NTFY_TOPIC`) does not affect a running loop. | Notifications skipped though `.env` looks right (`[notify] NTFY_TOPIC not set`). | Recreate to apply: `docker compose up -d --force-recreate`. Verify inside: `docker compose exec ralph_loop sh -c 'echo $NTFY_TOPIC'`. |
| 5 | **Under-declared dependency** — a slice truly needs another that wasn't listed under "Blocked by". | A slice could build on an unbuilt foundation. | Kickoff step "1b": the agent confirms its Blocked-by are CLOSED and stops `STATUS: BLOCKED` if it finds an undeclared dependency rather than stubbing. Lowest-issue-number-first selection also tends to respect real order. |
| 6 | **Umbrella issue selected as a slice** — the parent PRD issue carried `status:todo`. | Loop tries to "implement" the parent. | `next_issue` skips `PARENT_ISSUE`; the parent should not carry `status:todo`. |

## Recovery recipes

- **Issue stuck in `status:in-progress`** (its turn was killed mid-flight by a stop):
  the loop only re-picks `status:todo`, so reset it:
  `gh issue edit <N> --add-label status:todo --remove-label status:in-progress`.
- **Inspect / test the branch safely**: stop the loop first (it writes to the
  bind-mounted working tree). Then `pytest tests/studio` on the host venv.
- **Discard a turn's uncommitted partial work** (reversible): `git stash -u -- src tests docs`.
- **Confirm the loop is alive (not just idle)**: low CPU is normal (turns are
  network-bound). Check the active session transcript is growing:
  `docker compose exec ralph_loop sh -c 'ls -la /home/ralph/.claude/projects/-workspace/*.jsonl'`.

## Verifying completed slices

Don't trust card status alone. To confirm a closed slice was really built:
`git show --stat <commit>` (should touch core + skin + tests) and run
`pytest tests/studio` at the branch HEAD (the suite must be green — the
verification gate now enforces this per turn, but a manual sweep is cheap insurance).
