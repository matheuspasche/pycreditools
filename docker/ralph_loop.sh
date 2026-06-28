#!/usr/bin/env bash
# The "ralph loop": repeatedly invokes Claude Code headless, one PRD at a time.
# There is no approval gate (removed from docs/prd/IMPLEMENTATION_GUIDE.md) — a
# normal run goes kickoff -> implement -> validate -> DONE -> push -> next PRD,
# entirely within the agent's own kickoff turn. This loop just keeps feeding it
# the next PRD and handles the two things that need an outside retry: rate
# limits, and genuine STATUS: BLOCKED/ERROR (which stop the loop for a human).
set -uo pipefail   # no -e: we want to handle claude's exit code ourselves

cd /workspace

# Git identity + push auth. HOME=/root is deliberately isolated from the host
# (see Dockerfile) — no .gitconfig or git credentials get mounted in. Without
# this, the first "git commit" fails ("please tell me who you are") and the
# first "git push" / "gh ... sync" has no way to authenticate against GitHub.
git config --global user.name "${GIT_USER_NAME:-Matheus Pasche}"
git config --global user.email "${GIT_USER_EMAIL:-matheuspasche@gmail.com}"
if [ -n "${GH_TOKEN:-}" ]; then
    # gh already authenticates from the GH_TOKEN env var directly — no
    # `gh auth login` needed (it even refuses to, on purpose, while the env
    # var is set). This just makes plain `git push` use that same token too.
    gh auth setup-git
fi

MODEL="${CLAUDE_MODEL:-claude-sonnet-4-6}"           # never default to Opus
RATE_LIMIT_BACKOFF_SECONDS="${RATE_LIMIT_BACKOFF_SECONDS:-1800}"  # 30 min, Pro plan is tight
LOG_DIR="/workspace/.ralph/logs"
mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# Step 1: cheap, no-token check — are we even done?
# A non-DONE row looks like "| 02 | ... | TODO | |" (or IN PROGRESS, or the
# legacy AWAITING APPROVAL). If grep finds none, every PRD is DONE.
# ---------------------------------------------------------------------------
all_done() {
    ! grep -qE '^\| *[0-9]{2} *\|.*\| *(TODO|IN PROGRESS|AWAITING APPROVAL) *\|' \
        docs/prd/PROGRESS.md
}

# ---------------------------------------------------------------------------
# Step 2: pull the canonical kickoff prompt straight out of the guide, so the
# loop can never drift out of sync with what an interactive owner would paste.
# It lives between the first pair of ``` fences under "## 8. Kickoff prompt".
# ---------------------------------------------------------------------------
extract_kickoff_prompt() {
    awk '
        /^## 8\. Kickoff prompt/ { found = 1 }
        found && /^```$/ { fences++; if (fences == 1) next; if (fences == 2) exit }
        found && fences == 1 { print }
    ' docs/prd/IMPLEMENTATION_GUIDE.md \
    | sed 's|<fill path once>|/workspace|'
}

# ---------------------------------------------------------------------------
# Step 3: run one headless Claude turn. $1 = the prompt text. $2 (optional) =
# a session_id to --resume into (used only for rate-limit retries, so the
# retry continues the exact same conversation instead of starting fresh).
# Logs full JSON response to $LOG_DIR for audit.
# Sets globals: LAST_STATUS, LAST_SESSION_ID, LAST_OUTPUT_FILE
# ---------------------------------------------------------------------------
run_claude_turn() {
    local prompt="$1"
    local resume_id="${2:-}"
    local ts
    ts=$(date -u +%Y%m%dT%H%M%SZ)
    LAST_OUTPUT_FILE="$LOG_DIR/${ts}.json"

    local -a cmd=(claude --print "$prompt" --model "$MODEL" --output-format json --dangerously-skip-permissions)
    if [ -n "$resume_id" ]; then
        cmd+=(--resume "$resume_id")
    fi

    # stdout and stderr go to SEPARATE files on purpose. Claude Code sometimes
    # writes harmless warnings to stderr (e.g. a missing ~/.claude.json backup
    # notice) — if those land in the same file as the JSON, jq can't recover
    # from the leading garbage and fails to parse the whole file, silently
    # losing session_id and STATUS. The .stderr file is kept for debugging.
    "${cmd[@]}" > "$LAST_OUTPUT_FILE" 2>"${LAST_OUTPUT_FILE%.json}.stderr"
    local exit_code=$?

    # --output-format json returns one JSON object: "session_id" is what lets
    # a retry --resume into this same conversation, "result" is the agent's
    # final text — that's where the STATUS: sentinel line lives.
    LAST_SESSION_ID=$(jq -r '.session_id // empty' "$LAST_OUTPUT_FILE" 2>/dev/null)
    local result_text
    result_text=$(jq -r '.result // empty' "$LAST_OUTPUT_FILE" 2>/dev/null)
    LAST_STATUS=$(printf '%s' "$result_text" | grep -oE 'STATUS: [A-Z_]+' | tail -1 | awk '{print $2}')

    if [ -z "$LAST_STATUS" ]; then
        # Either claude failed before emitting valid JSON (no jq parse), or it
        # ran fine but never produced the STATUS: sentinel.
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
echo "[ralph_loop] starting — model=$MODEL"

while true; do
    if all_done; then
        notify.sh "Pycreditools Studio" "Todos os PRDs estão DONE — v1 completo." "default"
        echo "[ralph_loop] all PRDs DONE — exiting."
        break
    fi

    PROMPT=$(extract_kickoff_prompt)
    if [ -z "$PROMPT" ]; then
        notify.sh "Pycreditools Studio — ERRO" "Não consegui extrair o prompt de kickoff do guia. Parando." "urgent"
        echo "[ralph_loop] failed to extract kickoff prompt — check IMPLEMENTATION_GUIDE.md §8 format."
        exit 1
    fi

    echo "[ralph_loop] running kickoff turn (new session)..."
    CURRENT_PROMPT="$PROMPT"
    CURRENT_SESSION_ID=""
    run_claude_turn "$CURRENT_PROMPT"
    [ -n "$LAST_SESSION_ID" ] && CURRENT_SESSION_ID="$LAST_SESSION_ID"
    echo "[ralph_loop] turn finished — STATUS=$LAST_STATUS session=$CURRENT_SESSION_ID (log: $LAST_OUTPUT_FILE)"

    # A single PRD's worth of retries: only RATE_LIMITED loops back (--resuming
    # the same session) until the turn finally goes through. Every other status
    # is terminal for this PRD — DONE_AND_PUSHED moves to the next one,
    # BLOCKED/ERROR/CLI_ERROR/anything else stops the whole loop for a human.
    while [ "$LAST_STATUS" = "RATE_LIMITED" ]; do
        notify.sh "Pycreditools Studio — limite de uso" "Cota do plano atingida. Pausando ${RATE_LIMIT_BACKOFF_SECONDS}s e retomando a mesma sessão." "default"
        sleep "$RATE_LIMIT_BACKOFF_SECONDS"
        run_claude_turn "$CURRENT_PROMPT" "$CURRENT_SESSION_ID"
        [ -n "$LAST_SESSION_ID" ] && CURRENT_SESSION_ID="$LAST_SESSION_ID"
        echo "[ralph_loop] retry after rate limit finished — STATUS=$LAST_STATUS session=$CURRENT_SESSION_ID (log: $LAST_OUTPUT_FILE)"
    done

    case "$LAST_STATUS" in
        DONE_AND_PUSHED)
            notify.sh "PRD concluído" "Um PRD foi implementado, commitado e publicado. Seguindo para o próximo." "default"
            ;;

        BLOCKED)
            notify.sh "PRD bloqueado — precisa de você" "O agente parou e precisa de uma decisão sua. Veja: $LAST_OUTPUT_FILE" "urgent"
            echo "[ralph_loop] BLOCKED — stopping loop, this needs a human in a real session."
            break
            ;;

        AWAITING_APPROVAL)
            # Should not happen anymore (the gate was removed from the guide),
            # but if an old/cached prompt or a confused agent still emits this,
            # stop rather than guess — this status used to require a human
            # decision and still should if it ever shows up again.
            notify.sh "PRD em status inesperado" "Recebi STATUS: AWAITING_APPROVAL, que não devia mais existir. Parando para você olhar. Veja: $LAST_OUTPUT_FILE" "urgent"
            echo "[ralph_loop] unexpected AWAITING_APPROVAL — stopping loop, check IMPLEMENTATION_GUIDE.md is the version without the gate."
            break
            ;;

        ERROR|CLI_ERROR|*)
            notify.sh "Pycreditools Studio — ERRO" "Falha inesperada (STATUS=$LAST_STATUS). Veja: $LAST_OUTPUT_FILE" "urgent"
            echo "[ralph_loop] unrecoverable status '$LAST_STATUS' — stopping loop."
            break
            ;;
    esac
done

echo "[ralph_loop] stopped."
