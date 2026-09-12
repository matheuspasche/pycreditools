#!/usr/bin/env bash
# The ralph loop, v3 — the PAIR loop for the v0.6 engine map.
#
# v1 walked a PRD table; v2 (docker/ralph_loop.sh) ran one headless turn per GitHub
# issue and verified it with pytest. v3 keeps everything v2 learned (see
# docs/dev/ralph-loop-runbook.md for the seven guardrails) and replaces the single
# turn with a PAIR that argues:
#
#   implementer  — fresh session per ticket. Reads the spec, the map, the ticket AND its
#                  comments, criticises whether the ticket is even the right work now,
#                  implements test-first, commits. Never pushes.
#   auditor      — separate fresh session per ticket. Never trusts the implementer's
#                  summary: re-reads the cards, re-runs the gate, tries to break the
#                  tests, grades findings by severity.
#
# They ping-pong until `VERDICT: AGREED` or MAX_ROUNDS. Only then does the LOOP do the
# outward things: push, open the PR against release/v0.6, merge it, close the issue.
# There is no human gate — owner's ruling. The loop notifies by ntfy at every stop.
#
# Division of labour is deliberate: the agents never touch branch state, the PR, the
# issue labels or the merge, so a half-finished turn cannot leave the tracker lying.
set -uo pipefail   # no -e: claude's exit code is handled explicitly

cd /workspace

# ---------------------------------------------------------------------------
# Config (all overridable via env / .env)
# ---------------------------------------------------------------------------
REPO="${GH_REPO:-matheuspasche/pycreditools}"
BASE_BRANCH="${BASE_BRANCH:-release/v0.6}"       # integration branch for the version
PARENT_ISSUE="${PARENT_ISSUE:-156}"              # the spec umbrella — never implementable
MAP_ISSUE="${MAP_ISSUE:-111}"
QUEUE_LABEL="${QUEUE_LABEL:-ready-for-agent}"
SKIP_ISSUES="${SKIP_ISSUES:-}"                   # space-separated issue numbers to ignore
MODEL="${CLAUDE_MODEL:-claude-opus-5}"
EFFORT="${CLAUDE_EFFORT:-medium}"
MAX_ROUNDS="${MAX_ROUNDS:-8}"                    # audit rounds per ticket before stopping
CONTEXT_CAP_TOKENS="${CONTEXT_CAP_TOKENS:-450000}"   # per session; rotate when exceeded
RATE_LIMIT_BACKOFF_SECONDS="${RATE_LIMIT_BACKOFF_SECONDS:-1800}"
MERGE_METHOD="${MERGE_METHOD:---merge}"          # --merge | --squash | --rebase
LOG_DIR="${LOG_DIR:-/workspace/.ralph/logs/v06}"
PROMPT_DIR="${PROMPT_DIR:-/workspace/docker/prompts}"
mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# Git identity + auth. HOME is isolated from the host (see Dockerfile), so nothing is
# inherited — set it here or the first commit/push fails.
# ---------------------------------------------------------------------------
if [ "${RALPH_V06_LIB_ONLY:-0}" != "1" ]; then
    git config --global user.name "${GIT_USER_NAME:-Matheus Pasche}"
    git config --global user.email "${GIT_USER_EMAIL:-matheuspasche@gmail.com}"
    git config --global --add safe.directory /workspace
    [ -n "${GH_TOKEN:-}" ] && gh auth setup-git
fi

log() { echo "[ralph_v06] $*"; }

# ---------------------------------------------------------------------------
# Issue selection. Lowest-numbered open queue-labelled issue whose every "## Blocked by"
# reference is CLOSED. Parses only the LEADING "#N" of each list item — numbers inside a
# blocker's TITLE once created a phantom blocker that deadlocked the whole queue (v2
# guardrail #1).
# ---------------------------------------------------------------------------
# Pure half, so the tests can pin it: the blocker numbers an issue body declares.
parse_blockers() {
    printf '%s\n' "$1" | awk 'f; /^## Blocked by/{f=1}' \
        | grep -oE '^- #[0-9]+' | grep -oE '[0-9]+' | sort -u
}

blockers_all_closed() {
    local num="$1" body blockers b state
    body=$(gh issue view "$num" --repo "$REPO" --json body -q .body 2>/dev/null) || return 1
    blockers=$(parse_blockers "$body")
    for b in $blockers; do
        state=$(gh issue view "$b" --repo "$REPO" --json state -q .state 2>/dev/null)
        [ "$state" = "CLOSED" ] || return 1
    done
    return 0
}

is_skipped() {
    local n="$1" s
    for s in $SKIP_ISSUES; do [ "$s" = "$n" ] && return 0; done
    return 1
}

next_issue() {
    local nums n
    nums=$(gh issue list --repo "$REPO" --label "$QUEUE_LABEL" --state open \
             --json number --jq 'sort_by(.number)|.[].number' 2>/dev/null)
    for n in $nums; do
        [ "$n" = "$PARENT_ISSUE" ] && continue
        is_skipped "$n" && continue
        if blockers_all_closed "$n"; then echo "$n"; return 0; fi
    done
    return 0   # nothing actionable
}

count_open_queue() {
    gh issue list --repo "$REPO" --label "$QUEUE_LABEL" --state open \
        --json number --jq 'length' 2>/dev/null || echo 0
}

# ---------------------------------------------------------------------------
# One branch per ticket, cut fresh from the integration branch — CLAUDE.md's rule
# ("one ticket per branch, and every branch ends in a PR against release/v0.6").
# ---------------------------------------------------------------------------
# The cards are titled in pt-BR, so accents have to fold to ASCII before the branch name
# is built. Two ways that do NOT work here: a bracket class (`[àá]`) makes sed treat each
# BYTE of a multi-byte letter as a class member, which turned "ões" into "aaes"; and
# `iconv //TRANSLIT` under the container's C locale turns the same letter into "?", which
# then collapses to a dash ("decis-es"). Byte-safe alternation folds it correctly.
slugify() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' \
        | sed -E 's/(á|à|â|ã|ä)/a/g; s/(é|è|ê|ë)/e/g; s/(í|ì|î|ï)/i/g; s/(ó|ò|ô|õ|ö)/o/g; s/(ú|ù|û|ü)/u/g; s/ç/c/g; s/ñ/n/g' \
        | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' \
        | cut -c1-40 | sed -E 's/-+$//'
}

ensure_branch_for_issue() {
    local n="$1" title slug
    title=$(gh issue view "$n" --repo "$REPO" --json title -q .title 2>/dev/null)
    # Drop the "v0.6 · NN — " prefix the cards carry, keep the meaningful part.
    slug=$(slugify "$(printf '%s' "$title" | sed -E 's/^v0\.6 [^0-9]* ?[0-9]+ (—|-) //')")
    WORK_BRANCH="feat/${n}-${slug:-ticket}"
    git fetch origin --quiet || true
    if git show-ref --verify --quiet "refs/heads/$WORK_BRANCH"; then
        git checkout --quiet "$WORK_BRANCH"
    elif git ls-remote --exit-code --heads origin "$WORK_BRANCH" >/dev/null 2>&1; then
        git checkout --quiet -b "$WORK_BRANCH" "origin/$WORK_BRANCH"
    else
        git checkout --quiet -B "$WORK_BRANCH" "origin/$BASE_BRANCH"
    fi
    log "issue #$n on branch $WORK_BRANCH (base: $BASE_BRANCH)"
}

# ---------------------------------------------------------------------------
# Prompt assembly. Templates live in the bind-mounted tree, so they can be edited
# without rebuilding the image.
# ---------------------------------------------------------------------------
render_prompt() {
    local file="$1" n="$2" round="${3:-1}"
    sed -e "s|{{REPO}}|$REPO|g" -e "s|{{ISSUE}}|$n|g" -e "s|{{BRANCH}}|${WORK_BRANCH:-}|g" \
        -e "s|{{BASE}}|origin/$BASE_BRANCH|g" -e "s|{{ROUND}}|$round|g" \
        -e "s|{{MAX_ROUNDS}}|$MAX_ROUNDS|g" "$PROMPT_DIR/$file"
}

# ---------------------------------------------------------------------------
# Context size of a session, in tokens: the LAST assistant message's own request is the
# live context (input + cache_creation + cache_read) plus what it wrote. The result
# JSON's `usage` block is no good for this — it AGGREGATES every turn, so its cache_read
# runs to hundreds of thousands while the real context sits near 100k.
# Prints 0 when the transcript is unavailable.
# ---------------------------------------------------------------------------
session_context_tokens() {
    local sid="${1:-}" f
    [ -n "$sid" ] || { echo 0; return; }
    f="${TRANSCRIPT_DIR:-$HOME/.claude/projects/-workspace}/${sid}.jsonl"
    [ -f "$f" ] || { echo 0; return; }
    jq -s '[.[] | select(.type=="assistant") | .message.usage | select(. != null)] | last
           | if . == null then 0
             else (.input_tokens // 0) + (.cache_creation_input_tokens // 0)
                  + (.cache_read_input_tokens // 0) + (.output_tokens // 0) end' \
       "$f" 2>/dev/null || echo 0
}

over_context_cap() {
    local ctx="${1:-0}"
    [ "$ctx" -gt "$CONTEXT_CAP_TOKENS" ]
}

# ---------------------------------------------------------------------------
# Run one headless turn. $1 = role (impl|audit), $2 = prompt, $3 = session id to resume
# (empty for a fresh session).
# Sets: LAST_STATUS (the sentinel or an error pseudo-status), LAST_SESSION_ID,
#       LAST_OUTPUT_FILE, LAST_RESULT_TEXT, LAST_CTX_TOKENS.
# ---------------------------------------------------------------------------
run_claude_turn() {
    local role="$1" prompt="$2" resume_id="${3:-}" ts exit_code
    ts=$(date -u +%Y%m%dT%H%M%SZ)
    LAST_OUTPUT_FILE="$LOG_DIR/${ts}_${role}_${ISSUE}.json"

    local -a cmd=(claude --print "$prompt" --model "$MODEL" --effort "$EFFORT"
                  --output-format json --dangerously-skip-permissions)
    [ -n "$resume_id" ] && cmd+=(--resume "$resume_id")

    # stdout (the JSON) and stderr (occasional harmless warnings) go to separate files so
    # stray stderr cannot corrupt the JSON jq parses.
    "${cmd[@]}" > "$LAST_OUTPUT_FILE" 2>"${LAST_OUTPUT_FILE%.json}.stderr"
    exit_code=$?

    LAST_SESSION_ID=$(jq -r '.session_id // empty' "$LAST_OUTPUT_FILE" 2>/dev/null)
    LAST_RESULT_TEXT=$(jq -r '.result // empty' "$LAST_OUTPUT_FILE" 2>/dev/null)
    LAST_CTX_TOKENS=$(session_context_tokens "$LAST_SESSION_ID")
    [ -n "$LAST_CTX_TOKENS" ] || LAST_CTX_TOKENS=0

    LAST_STATUS=$(sentinel_of "$role" "$LAST_RESULT_TEXT")

    if [ -z "$LAST_STATUS" ]; then
        # Prefer the CLI's STRUCTURED 429 over text-matching: grepping the raw JSON for
        # "429" gave false positives (it matched "429" inside token counts) and the
        # wording varies ("session limit" / "usage limit" / "5-hour limit reached").
        local api_err
        api_err=$(jq -r '.api_error_status // empty' "$LAST_OUTPUT_FILE" 2>/dev/null)
        if [ "$api_err" = "429" ] || is_rate_limited_file "$LAST_OUTPUT_FILE"; then
            LAST_STATUS="RATE_LIMITED"
        elif [ "$exit_code" -ne 0 ]; then
            LAST_STATUS="CLI_ERROR"
        else
            LAST_STATUS="NO_SENTINEL"
        fi
    fi
    log "$role turn: status=$LAST_STATUS ctx=${LAST_CTX_TOKENS}tok session=$LAST_SESSION_ID log=$(basename "$LAST_OUTPUT_FILE")"
}

# The sentinel each role ends on. Pure, so the tests can pin it.
sentinel_of() {
    local role="$1" text="$2" key="STATUS"
    [ "$role" = "audit" ] && key="VERDICT"
    printf '%s' "$text" | grep -oE "${key}: [A-Z_]+" | tail -1 | awk '{print $2}'
}

# Rate-limit detection over a result file (structured status is checked by the caller).
is_rate_limited_file() {
    grep -qiE 'session limit|usage limit|rate limit|limit reached|too many requests|try again later' \
        "$1" "${1%.json}.stderr" 2>/dev/null
}

# ---------------------------------------------------------------------------
# How long to wait out a rate limit. On a 429 the CLI's result text says when the quota
# resets ("You've hit your session limit · resets 10:30pm (UTC)"). Sleep until ONE MINUTE
# PAST that reset instead of polling blindly — the blind 30-min poll once burned ~4.5h of
# retries waiting out a single session window (v2 guardrail #7).
#
# Pure + testable: result text from $1 (default: $LAST_OUTPUT_FILE's .result), "now" from
# $NOW_EPOCH. Any unparseable wording falls back to the fixed backoff.
# ---------------------------------------------------------------------------
rate_limit_backoff_seconds() {
    local result_text="${1:-$(jq -r '.result // empty' "${LAST_OUTPUT_FILE:-/dev/null}" 2>/dev/null)}"
    local now="${NOW_EPOCH:-$(date +%s)}"
    local clause timepart tz base target sleep_s

    clause=$(printf '%s' "$result_text" \
        | grep -oiE 'resets?[[:space:]]+[0-9]{1,2}(:[0-9]{2})?[[:space:]]*(am|pm)?[[:space:]]*\(?[A-Za-z]{2,5}\)?' \
        | head -1)
    [ -z "$clause" ] && { echo "$RATE_LIMIT_BACKOFF_SECONDS"; return; }

    timepart=$(printf '%s' "$clause" | grep -oiE '[0-9]{1,2}(:[0-9]{2})?[[:space:]]*(am|pm)?' | head -1)
    tz=$(printf '%s' "$clause" | grep -oiE '[A-Za-z]{2,5}\)?$' | tr -d '()')
    # "resets 11am" with no zone: the trailing letters ARE the meridiem, not a timezone.
    # Feeding them on as one ("11am am") makes `date` fail and silently drops the whole
    # hint into the fixed fallback — the wording without a zone is common enough that this
    # was the one parse that still lost its reset instant.
    printf '%s' "$tz" | grep -qiE '^(am|pm)$' && tz=""
    [ -z "$tz" ] && tz="UTC"

    # The hint carries a time-of-day but no DATE — anchor to now's UTC date and roll
    # forward a day when that instant already passed.
    base=$(date -u -d "@$now" +%Y-%m-%d 2>/dev/null) || { echo "$RATE_LIMIT_BACKOFF_SECONDS"; return; }
    target=$(date -d "$base $timepart $tz" +%s 2>/dev/null)
    [ -z "$target" ] && { echo "$RATE_LIMIT_BACKOFF_SECONDS"; return; }
    [ "$target" -le "$now" ] && target=$((target + 86400))

    sleep_s=$((target - now + 60))
    [ "$sleep_s" -lt 60 ] && sleep_s=60
    # A reset further out than MAX_SLEEP (a weekly limit, or a misparse) is slept in
    # MAX_SLEEP-sized bites: wake, retry, re-parse the fresh hint, sleep the remainder.
    # v2 fell back to the fixed 30-min poll here instead, which silently restored the
    # blind polling that guardrail #7 was written to kill — a 13h reset cost 27 wasted
    # retries. One retry per 6h strictly dominates it, and a misparse can no longer
    # sleep away a whole day.
    [ "$sleep_s" -gt "${MAX_SLEEP_SECONDS:-21600}" ] && sleep_s="${MAX_SLEEP_SECONDS:-21600}"
    echo "$sleep_s"
}

# ---------------------------------------------------------------------------
# A turn that survives rate limits and context exhaustion.
#   $1 = role, $2 = prompt, $3 = name of the session variable (IMPL_SESSION/AUDIT_SESSION)
# On a 429: sleep to the reset and RESUME the same conversation.
# Over the context cap: clear the session id so the NEXT turn of that role starts fresh —
# the work itself lives in commits, and both prompts are written to be re-enterable.
# ---------------------------------------------------------------------------
turn_with_retries() {
    local role="$1" prompt="$2" var="$3" sid backoff resume_at
    eval "sid=\${$var:-}"
    run_claude_turn "$role" "$prompt" "$sid"
    while [ "$LAST_STATUS" = "RATE_LIMITED" ]; do
        backoff=$(rate_limit_backoff_seconds)
        resume_at=$(date -u -d "+${backoff} seconds" +%H:%MZ 2>/dev/null || echo '?')
        notify.sh "v0.6 — limite de uso" "Cota atingida na #$ISSUE ($role). Durmo ${backoff}s e retomo ~${resume_at} (1 min apos o reset informado)." "default"
        log "#$ISSUE $role rate-limited — sleeping ${backoff}s, resume ~${resume_at}"
        sleep "$backoff"
        run_claude_turn "$role" "$prompt" "${LAST_SESSION_ID:-$sid}"
    done
    [ -n "${LAST_SESSION_ID:-}" ] && eval "$var=\"\$LAST_SESSION_ID\""
    if over_context_cap "${LAST_CTX_TOKENS:-0}"; then
        notify.sh "v0.6 — sessao rotacionada" "A sessao $role da #$ISSUE passou de ${CONTEXT_CAP_TOKENS} tokens de contexto (${LAST_CTX_TOKENS}). A proxima rodada comeca fresca; o trabalho esta nos commits." "low"
        log "#$ISSUE $role over context cap (${LAST_CTX_TOKENS} > $CONTEXT_CAP_TOKENS) — rotating session"
        eval "$var=\"\""
    fi
}

# ---------------------------------------------------------------------------
# Independent verification gate. Neither agent's "green" is taken on trust: the loop
# re-runs the suite itself before it will push or merge anything (v2 guardrail #3).
# Studio is out of scope for the v0.6 map (ticket 13 owns it), hence the ignore.
# ---------------------------------------------------------------------------
verify_turn() {
    local py="python3" pt=0 rf=0 vlog="$LOG_DIR/verify_${ISSUE}.log"
    [ -x ".venv-linux/bin/python" ] && py=".venv-linux/bin/python"
    log "verifying #$ISSUE (pytest + ruff) before accepting agreement..."
    "$py" -m pytest tests --ignore=tests/studio -q > "$vlog" 2>&1 || pt=$?
    if [ -x ".venv-linux/bin/ruff" ]; then
        .venv-linux/bin/ruff check src/pycreditools/engine tests/engine >> "$vlog" 2>&1 || rf=$?
    fi
    if [ "$pt" -ne 0 ] || [ "$rf" -ne 0 ]; then
        log "verify FAILED for #$ISSUE (pytest=$pt ruff=$rf) — see $vlog"
        return 1
    fi
    log "verify OK for #$ISSUE"
    return 0
}

# ---------------------------------------------------------------------------
# The outward half: push, PR against the integration branch, merge, close the issue.
# GitHub refuses a self-approval, so "approve" here is the merge itself plus a comment
# recording that the pair agreed — the owner's ruling, made auditable.
# ---------------------------------------------------------------------------
land_ticket() {
    local n="$1" rounds="$2" title pr body
    if ! git push -u origin "$WORK_BRANCH" 2>&1 | tail -2; then
        notify.sh "v0.6 — falha no push" "A #$n foi implementada e auditada, mas o push falhou. Parando." "urgent"
        log "push failed for #$n"
        return 1
    fi
    title=$(gh issue view "$n" --repo "$REPO" --json title -q .title 2>/dev/null)
    if ! gh pr view "$WORK_BRANCH" --repo "$REPO" >/dev/null 2>&1; then
        body=$(printf 'Closes #%s.\n\nImplementado e auditado pelo par headless do ralph loop v3 (`docker/ralph_loop_v06.sh`): uma sessao implementa, outra audita a frio contra a spec (`docs/engine/spec/v06-architecture.md`), o mapa (#%s) e o card com seus comentarios. Acordo alcancado em **%s** rodada(s) de critica; o gate (`pytest tests --ignore=tests/studio` + `ruff` na superficie v0.6) foi re-executado pelo loop, nao pelos agentes.\n\nLogs dos turnos: `.ralph/logs/v06/`.\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n' \
            "$n" "$MAP_ISSUE" "$rounds")
        gh pr create --repo "$REPO" --base "$BASE_BRANCH" --head "$WORK_BRANCH" \
            --title "$title (#$n)" --body "$body" >/dev/null 2>&1 \
            || log "WARN: could not create PR for #$n"
    fi
    pr=$(gh pr view "$WORK_BRANCH" --repo "$REPO" --json number -q .number 2>/dev/null)
    [ -n "$pr" ] || { log "no PR for #$n — stopping"; return 1; }
    gh pr comment "$pr" --repo "$REPO" \
        --body "Par implementador x auditor em acordo apos ${rounds} rodada(s). Gate re-executado pelo loop: verde." \
        >/dev/null 2>&1 || true
    if gh pr merge "$pr" --repo "$REPO" $MERGE_METHOD --delete-branch >/dev/null 2>&1; then
        log "PR #$pr merged into $BASE_BRANCH"
    else
        notify.sh "v0.6 — merge falhou" "PR #$pr (issue #$n) nao mergeou. A branch $WORK_BRANCH esta no remoto. Parando." "urgent"
        log "merge failed for PR #$pr"
        return 1
    fi
    # A merge into release/v0.6 is not on the default branch, so GitHub never closes the
    # issue by itself — close it here or the queue re-picks work that is already done.
    gh issue close "$n" --repo "$REPO" --reason completed >/dev/null 2>&1 || true
    gh issue edit "$n" --repo "$REPO" --remove-label "$QUEUE_LABEL" >/dev/null 2>&1 || true
    git checkout --quiet "$BASE_BRANCH" 2>/dev/null \
        || git checkout --quiet -B "$BASE_BRANCH" "origin/$BASE_BRANCH"
    git pull --quiet --ff-only origin "$BASE_BRANCH" 2>/dev/null || true
    notify.sh "#$n concluida" "PR #$pr mergeado em $BASE_BRANCH apos ${rounds} rodada(s) de auditoria. Issue fechada. Seguindo para o proximo ticket." "default"
    return 0
}

issue_note() {
    local n="$1" text="$2"
    gh issue comment "$n" --repo "$REPO" --body "$(printf '%s' "$text" | head -c 60000)" \
        >/dev/null 2>&1 || true
}

# ---------------------------------------------------------------------------
# One ticket, end to end: implement -> audit -> argue -> land. Returns 0 when the ticket
# landed, 1 when the loop must stop for a human.
# ---------------------------------------------------------------------------
run_ticket() {
    local n="$1" round=0 impl_report audit_findings audit_prompt fix_prompt
    IMPL_SESSION=""; AUDIT_SESSION=""
    ensure_branch_for_issue "$n"

    turn_with_retries impl "$(render_prompt v06_implementer.md "$n" 1)" IMPL_SESSION
    impl_report="$LAST_RESULT_TEXT"

    case "$LAST_STATUS" in
        DONE) ;;
        WRONG_TICKET)
            issue_note "$n" "$(printf 'O par headless parou antes de implementar: o ticket nao parece ser o trabalho certo agora.\n\n%s' "$impl_report")"
            gh issue edit "$n" --repo "$REPO" --add-label "needs-triage" >/dev/null 2>&1 || true
            notify.sh "v0.6 — ticket errado (#$n)" "O implementador sustenta que a #$n nao e o trabalho certo agora. Comentei na issue com a evidencia e parei." "urgent"
            return 1 ;;
        BLOCKED)
            issue_note "$n" "$(printf 'O par headless parou: BLOCKED.\n\n%s' "$impl_report")"
            gh issue edit "$n" --repo "$REPO" --add-label "needs-info" >/dev/null 2>&1 || true
            notify.sh "v0.6 — issue bloqueada (#$n)" "Precisa de uma decisao sua. Comentei na issue. Log: $LAST_OUTPUT_FILE" "urgent"
            return 1 ;;
        *)
            notify.sh "v0.6 — ERRO na #$n" "Implementador terminou com STATUS=$LAST_STATUS. Log: $LAST_OUTPUT_FILE" "urgent"
            return 1 ;;
    esac

    while [ "$round" -lt "$MAX_ROUNDS" ]; do
        round=$((round + 1))
        if [ -n "$AUDIT_SESSION" ] && [ "$round" -gt 1 ]; then
            audit_prompt=$(printf 'Audit round %s of %s on #%s. The implementer answered your findings:\n\n--- IMPLEMENTER RESPONSE ---\n%s\n--- END ---\n\nRe-read `git diff origin/%s...HEAD` (it moved), re-run the gate yourself, and check each of your earlier findings: fixed, worked around, or correctly argued down. Raise anything new the fix introduced. End with exactly one VERDICT line.' \
                "$round" "$MAX_ROUNDS" "$n" "$impl_report" "$BASE_BRANCH")
        else
            audit_prompt=$(render_prompt v06_auditor.md "$n" "$round")
            if [ "$round" -gt 1 ]; then
                audit_prompt=$(printf '%s\n\n## Continuation\n\nThis audit session is fresh (the previous one hit its context cap), but the work is on round %s. The implementer last reported:\n\n%s\n' \
                    "$audit_prompt" "$round" "$impl_report")
            fi
        fi
        turn_with_retries audit "$audit_prompt" AUDIT_SESSION
        audit_findings="$LAST_RESULT_TEXT"

        case "$LAST_STATUS" in
            AGREED)
                log "#$n: pair agreed after $round round(s)"
                if ! verify_turn; then
                    issue_note "$n" "O par declarou acordo na #$n, mas o gate do loop (pytest/ruff) falhou. Nada foi empurrado. Veja \`.ralph/logs/v06/verify_${n}.log\`."
                    notify.sh "v0.6 — verificacao falhou (#$n)" "Par em acordo mas pytest/ruff vermelho. NADA foi empurrado. Veja .ralph/logs/v06/verify_${n}.log" "urgent"
                    return 1
                fi
                land_ticket "$n" "$round" || return 1
                return 0 ;;
            CHANGES_REQUESTED)
                log "#$n: audit round $round requested changes"
                fix_prompt=$(printf 'The auditor reviewed your work on #%s and asked for changes (round %s of %s). Their findings, verbatim:\n\n--- AUDIT ---\n%s\n--- END ---\n\nFor each finding: fix it, or argue it down with evidence (file:line, a command and its output) if the auditor is wrong — do not cave to a wrong finding and do not hand-wave a right one. NITs may be ignored. Re-run the gate, commit, then report what you changed and what you pushed back on. End with exactly one STATUS line.' \
                    "$n" "$round" "$MAX_ROUNDS" "$audit_findings")
                turn_with_retries impl "$fix_prompt" IMPL_SESSION
                impl_report="$LAST_RESULT_TEXT"
                if [ "$LAST_STATUS" != "DONE" ]; then
                    issue_note "$n" "$(printf 'O implementador parou na rodada %s com STATUS=%s.\n\n%s' "$round" "$LAST_STATUS" "$impl_report")"
                    notify.sh "v0.6 — implementador parou (#$n)" "STATUS=$LAST_STATUS na rodada $round. Log: $LAST_OUTPUT_FILE" "urgent"
                    return 1
                fi ;;
            ESCALATE)
                issue_note "$n" "$(printf 'O par headless empatou numa decisao de projeto que os cards nao resolvem (rodada %s).\n\n%s' "$round" "$audit_findings")"
                notify.sh "v0.6 — empate na #$n" "Implementador e auditor discordam sobre projeto, rodada $round. As duas posicoes estao na issue." "urgent"
                return 1 ;;
            *)
                notify.sh "v0.6 — ERRO na auditoria da #$n" "Auditor terminou com VERDICT=$LAST_STATUS. Log: $LAST_OUTPUT_FILE" "urgent"
                return 1 ;;
        esac
    done

    issue_note "$n" "$(printf 'O par headless nao chegou a acordo em %s rodadas. O trabalho esta na branch `%s` (nao empurrada). Ultimos achados do auditor:\n\n%s' "$MAX_ROUNDS" "$WORK_BRANCH" "$audit_findings")"
    notify.sh "v0.6 — sem acordo na #$n" "$MAX_ROUNDS rodadas sem acordo. Trabalho preservado em $WORK_BRANCH, nada empurrado. Olhe os achados na issue." "urgent"
    log "#$n: no agreement in $MAX_ROUNDS rounds — stopping for a human"
    return 1
}

# ---------------------------------------------------------------------------
# Main loop. Sourced with RALPH_V06_LIB_ONLY=1, the file defines the functions and stops
# here — that is how docker/tests/test_ralph_v06.sh pins the pure helpers.
# ---------------------------------------------------------------------------
main() {
log "starting — model=$MODEL effort=$EFFORT rounds<=$MAX_ROUNDS ctx_cap=$CONTEXT_CAP_TOKENS base=$BASE_BRANCH"
notify.sh "v0.6 — loop iniciado" "Par implementador x auditor no ar. Modelo $MODEL (effort $EFFORT), ate $MAX_ROUNDS rodadas por ticket, PRs contra $BASE_BRANCH." "low"

while true; do
    ISSUE=$(next_issue)
    if [ -z "$ISSUE" ]; then
        remaining=$(count_open_queue)
        if [ "$remaining" -gt 1 ]; then
            notify.sh "v0.6 — fila travada" "Restam $remaining issue(s) com $QUEUE_LABEL, todas bloqueadas por dependencia aberta. Veja o grafo de Blocked by." "urgent"
            log "$remaining queue issue(s) left but all blocked — stopping for a human."
        else
            notify.sh "v0.6 — fila vazia" "Nenhum ticket acionavel restante. Revise $BASE_BRANCH." "default"
            log "queue empty — nothing actionable. Review $BASE_BRANCH."
        fi
        break
    fi
    log "next ticket: #$ISSUE"
    run_ticket "$ISSUE" || break
done

log "stopped."
}

# Sourced with RALPH_V06_LIB_ONLY=1 the file only defines functions — that is how
# docker/tests/test_ralph_v06.sh pins the pure helpers without launching anything.
if [ "${RALPH_V06_LIB_ONLY:-0}" != "1" ]; then
    main
fi
