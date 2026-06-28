#!/usr/bin/env bash
# The "ralph loop" — v2, issue-driven.
#
# v1 walked a PRD table in docs/prd/PROGRESS.md (one coarse PRD per turn). v2 runs
# a single PRD that was sliced into many GitHub issues (the PRD 12 redesign): each
# turn it grabs the next unblocked `status:todo` issue, hands it to a fresh headless
# Claude turn to implement test-first, then the LOOP (not the agent) does all the
# stateful/outward bits — labels, closing the issue, pushing, and keeping ONE pull
# request open for the whole PRD. The owner evaluates at the END, by reviewing that
# single PR; there is no per-issue approval gate.
#
# Division of labour (deliberate — keeps the cheap agent's job small and verifiable):
#   agent turn : read the issue + its context, implement with TDD, run tests/ruff
#                green, COMMIT (no push), end with a STATUS: sentinel.
#   loop       : pick the issue, set labels, push, open/refresh the PR, close the
#                issue, handle rate limits, stop for a human on BLOCKED/ERROR.
set -uo pipefail   # no -e: we handle claude's exit code ourselves

cd /workspace

# ---------------------------------------------------------------------------
# Config (all overridable via env / .env)
# ---------------------------------------------------------------------------
REPO="${GH_REPO:-matheuspasche/pycreditools}"
BASE_BRANCH="${BASE_BRANCH:-feature/gui-streamlit-studio}"   # where v1 lives; PR target
WORK_BRANCH="${WORK_BRANCH:-prd-12-studio-v2}"               # the single PRD-12 branch
PARENT_ISSUE="${PARENT_ISSUE:-16}"
PR_TITLE="${PR_TITLE:-PRD 12: Studio v2 — Central Bancada Redesign}"
TODO_LABEL="status:todo"
PROGRESS_LABEL="status:in-progress"
DONE_LABEL="status:done"
MODEL="${CLAUDE_MODEL:-claude-sonnet-4-6}"                   # never default to Opus
RATE_LIMIT_BACKOFF_SECONDS="${RATE_LIMIT_BACKOFF_SECONDS:-1800}"
LOG_DIR="/workspace/.ralph/logs"
mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# Git identity + auth. HOME is isolated from the host (see Dockerfile), so nothing
# is inherited — set it here or the first commit/push fails.
# ---------------------------------------------------------------------------
git config --global user.name "${GIT_USER_NAME:-Matheus Pasche}"
git config --global user.email "${GIT_USER_EMAIL:-matheuspasche@gmail.com}"
# The repo is a bind-mount owned by the host user, not `ralph` — without this git
# refuses to operate ("detected dubious ownership in repository").
git config --global --add safe.directory /workspace
if [ -n "${GH_TOKEN:-}" ]; then
    gh auth setup-git   # make plain `git push` use the same token gh already has
fi

# ---------------------------------------------------------------------------
# Make sure we are on the single PRD-12 work branch (create from BASE if needed).
# ---------------------------------------------------------------------------
ensure_branch() {
    git fetch origin --quiet || true
    if git show-ref --verify --quiet "refs/heads/$WORK_BRANCH"; then
        git checkout --quiet "$WORK_BRANCH"
    elif git ls-remote --exit-code --heads origin "$WORK_BRANCH" >/dev/null 2>&1; then
        git checkout --quiet -b "$WORK_BRANCH" "origin/$WORK_BRANCH"
    else
        git checkout --quiet -B "$WORK_BRANCH" "origin/$BASE_BRANCH" 2>/dev/null \
            || git checkout --quiet -B "$WORK_BRANCH" "$BASE_BRANCH"
    fi
    echo "[ralph_loop] on branch $WORK_BRANCH (PR base: $BASE_BRANCH)"
}

# ---------------------------------------------------------------------------
# Issue selection. Returns (echoes) the number of the lowest-numbered open
# `status:todo` issue whose every "## Blocked by" reference is already closed.
# Prints nothing if no issue is currently actionable.
# ---------------------------------------------------------------------------
blockers_all_closed() {
    local num="$1" body blockers b state
    body=$(gh issue view "$num" --repo "$REPO" --json body -q .body 2>/dev/null) || return 1
    # Only the "## Blocked by" section carries dependencies — parsing the whole body
    # would wrongly treat the parent "#16" reference as a blocker.
    blockers=$(printf '%s\n' "$body" | awk 'f; /^## Blocked by/{f=1}' \
                 | grep -oE '#[0-9]+' | tr -d '#' | sort -u)
    for b in $blockers; do
        state=$(gh issue view "$b" --repo "$REPO" --json state -q .state 2>/dev/null)
        [ "$state" = "CLOSED" ] || return 1
    done
    return 0
}

next_issue() {
    local nums n
    nums=$(gh issue list --repo "$REPO" --label "$TODO_LABEL" --state open \
             --json number --jq 'sort_by(.number)|.[].number' 2>/dev/null)
    for n in $nums; do
        if blockers_all_closed "$n"; then
            echo "$n"
            return 0
        fi
    done
    return 0   # nothing actionable
}

count_open_todo() {
    gh issue list --repo "$REPO" --label "$TODO_LABEL" --state open \
        --json number --jq 'length' 2>/dev/null || echo 0
}

# ---------------------------------------------------------------------------
# Keep exactly one PR open for the whole PRD. Idempotent: creates it on first call
# (after the branch has been pushed), no-ops afterwards.
# ---------------------------------------------------------------------------
ensure_pr() {
    if gh pr view "$WORK_BRANCH" --repo "$REPO" >/dev/null 2>&1; then
        return 0
    fi
    gh pr create --repo "$REPO" --base "$BASE_BRANCH" --head "$WORK_BRANCH" \
        --title "$PR_TITLE" \
        --body "Implements the PRD 12 slices (parent #${PARENT_ISSUE}). Each commit closes one slice issue. Review the whole PR at the end of the PRD." \
        2>&1 | tail -1 || echo "[ralph_loop] WARN: could not create PR (continuing)"
}

# ---------------------------------------------------------------------------
# The kickoff prompt for one issue. The agent only reads + implements + commits;
# the loop owns labels, closing, push and the PR.
# ---------------------------------------------------------------------------
build_kickoff() {
    local n="$1"
    cat <<EOF
You are an autonomous coding agent in a dockerized loop, implementing ONE GitHub
issue of the Pycreditools Studio v2 redesign. You have NO prior context — everything
you need is in the repo and the issue. Repo: ${REPO}. Your issue THIS turn: #${n}.

You are already on branch \`${WORK_BRANCH}\` — do NOT switch or create branches, do
NOT push, do NOT touch any other issue, never force-push or rewrite history.

Do this end-to-end in this single turn:
1. Read issue #${n} in full: \`gh issue view ${n} --repo ${REPO}\`. Then read the
   context it points to: the parent PRD #${PARENT_ISSUE}, the ADRs it names under
   docs/adr/, and docs/redesign/studio-redesign.md (per-critique map + glossary).
2. Implement the slice TEST-FIRST (TDD), red->green->refactor:
   - write the failing core test in tests/studio/parity/ first (pure: data in ->
     plain data out), watch it fail, then implement in src/pycreditools/studio/;
   - add only thin tests/studio/apptest/ coverage for page wiring.
3. Obey the hard rules from the issue: NEVER touch the package engine (anything in
   src/pycreditools/ outside studio/ and gui/); all logic lives in studio/ with no
   \`import streamlit\`; only gui/ imports streamlit; the
   test_core_has_no_streamlit_import boundary test must stay green. UI copy pt-BR,
   identifiers English.
4. Run \`pytest tests/studio\` and \`ruff check src tests\` — everything green.
5. COMMIT your work with a clear message that references #${n} (e.g.
   "feat(studio): <slice> (#${n})"). Do NOT push — the loop pushes and manages the
   issue state and the pull request.
6. End your FINAL message with exactly ONE sentinel line:
   - \`STATUS: DONE\`    — all tests/ruff green and committed; ready for the loop to push/close.
   - \`STATUS: BLOCKED\` — genuinely ambiguous or a real dependency is missing; explain why.
   - \`STATUS: ERROR\`   — an unrecoverable failure you could not resolve.

Start by printing a 5-bullet plan for issue #${n}, then implement.
EOF
}

# ---------------------------------------------------------------------------
# Run one headless Claude turn. $1 = prompt, $2 (optional) = session id to --resume.
# Sets: LAST_STATUS, LAST_SESSION_ID, LAST_OUTPUT_FILE
# ---------------------------------------------------------------------------
run_claude_turn() {
    local prompt="$1" resume_id="${2:-}" ts exit_code result_text
    ts=$(date -u +%Y%m%dT%H%M%SZ)
    LAST_OUTPUT_FILE="$LOG_DIR/${ts}.json"

    local -a cmd=(claude --print "$prompt" --model "$MODEL" --output-format json --dangerously-skip-permissions)
    [ -n "$resume_id" ] && cmd+=(--resume "$resume_id")

    # stdout (the JSON) and stderr (occasional harmless warnings) go to separate
    # files so stray stderr can't corrupt the JSON jq parses.
    "${cmd[@]}" > "$LAST_OUTPUT_FILE" 2>"${LAST_OUTPUT_FILE%.json}.stderr"
    exit_code=$?

    LAST_SESSION_ID=$(jq -r '.session_id // empty' "$LAST_OUTPUT_FILE" 2>/dev/null)
    result_text=$(jq -r '.result // empty' "$LAST_OUTPUT_FILE" 2>/dev/null)
    LAST_STATUS=$(printf '%s' "$result_text" | grep -oE 'STATUS: [A-Z_]+' | tail -1 | awk '{print $2}')

    if [ -z "$LAST_STATUS" ]; then
        if grep -qiE 'rate limit|usage limit|try again later|429' "$LAST_OUTPUT_FILE" "${LAST_OUTPUT_FILE%.json}.stderr"; then
            LAST_STATUS="RATE_LIMITED"
        elif [ "$exit_code" -ne 0 ]; then
            LAST_STATUS="CLI_ERROR"
        else
            LAST_STATUS="ERROR"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
echo "[ralph_loop] starting — model=$MODEL repo=$REPO"
ensure_branch

while true; do
    ISSUE=$(next_issue)

    if [ -z "$ISSUE" ]; then
        remaining=$(count_open_todo)
        if [ "$remaining" -gt 0 ]; then
            notify.sh "PRD 12 — travado" "Restam $remaining issue(s) status:todo, mas todas bloqueadas por dependências abertas. Veja o grafo de Blocked by." "urgent"
            echo "[ralph_loop] $remaining todo issue(s) left but all blocked — stopping for a human."
            break
        fi
        ensure_pr
        notify.sh "PRD 12 concluída" "Todas as issues da PRD 12 foram implementadas e fechadas. Revise o PR de $WORK_BRANCH." "default"
        echo "[ralph_loop] no open status:todo issues — PRD 12 complete. Review the PR."
        break
    fi

    echo "[ralph_loop] next issue: #$ISSUE"
    gh issue edit "$ISSUE" --repo "$REPO" --add-label "$PROGRESS_LABEL" --remove-label "$TODO_LABEL" >/dev/null 2>&1 || true

    PROMPT=$(build_kickoff "$ISSUE")
    CURRENT_SESSION_ID=""
    run_claude_turn "$PROMPT"
    [ -n "$LAST_SESSION_ID" ] && CURRENT_SESSION_ID="$LAST_SESSION_ID"
    echo "[ralph_loop] issue #$ISSUE turn finished — STATUS=$LAST_STATUS session=$CURRENT_SESSION_ID (log: $LAST_OUTPUT_FILE)"

    # Only RATE_LIMITED retries (resuming the same conversation) until it goes through.
    while [ "$LAST_STATUS" = "RATE_LIMITED" ]; do
        notify.sh "PRD 12 — limite de uso" "Cota atingida na issue #$ISSUE. Pausando ${RATE_LIMIT_BACKOFF_SECONDS}s e retomando a mesma sessão." "default"
        sleep "$RATE_LIMIT_BACKOFF_SECONDS"
        run_claude_turn "$PROMPT" "$CURRENT_SESSION_ID"
        [ -n "$LAST_SESSION_ID" ] && CURRENT_SESSION_ID="$LAST_SESSION_ID"
        echo "[ralph_loop] issue #$ISSUE retry finished — STATUS=$LAST_STATUS (log: $LAST_OUTPUT_FILE)"
    done

    case "$LAST_STATUS" in
        DONE|DONE_AND_PUSHED)
            # The loop owns the outward/stateful steps so the agent can't half-do them.
            if git push -u origin "$WORK_BRANCH" 2>&1 | tail -2; then
                ensure_pr
                gh issue edit "$ISSUE" --repo "$REPO" --add-label "$DONE_LABEL" --remove-label "$PROGRESS_LABEL" >/dev/null 2>&1 || true
                gh issue close "$ISSUE" --repo "$REPO" --reason completed >/dev/null 2>&1 || true
                notify.sh "Issue #$ISSUE concluída" "Slice implementada, commitada e empurrada para $WORK_BRANCH. Seguindo." "default"
            else
                gh issue edit "$ISSUE" --repo "$REPO" --add-label "$TODO_LABEL" --remove-label "$PROGRESS_LABEL" >/dev/null 2>&1 || true
                notify.sh "PRD 12 — falha no push" "Issue #$ISSUE foi implementada mas o push falhou. Parando para você olhar." "urgent"
                echo "[ralph_loop] push failed for #$ISSUE — stopping."
                break
            fi
            ;;

        BLOCKED)
            gh issue edit "$ISSUE" --repo "$REPO" --add-label "$TODO_LABEL" --remove-label "$PROGRESS_LABEL" >/dev/null 2>&1 || true
            notify.sh "PRD 12 — issue bloqueada" "Issue #$ISSUE precisa de uma decisão sua. Veja: $LAST_OUTPUT_FILE" "urgent"
            echo "[ralph_loop] #$ISSUE BLOCKED — stopping for a human."
            break
            ;;

        ERROR|CLI_ERROR|*)
            gh issue edit "$ISSUE" --repo "$REPO" --add-label "$TODO_LABEL" --remove-label "$PROGRESS_LABEL" >/dev/null 2>&1 || true
            notify.sh "PRD 12 — ERRO" "Falha inesperada na issue #$ISSUE (STATUS=$LAST_STATUS). Veja: $LAST_OUTPUT_FILE" "urgent"
            echo "[ralph_loop] unrecoverable status '$LAST_STATUS' on #$ISSUE — stopping."
            break
            ;;
    esac
done

echo "[ralph_loop] stopped."
