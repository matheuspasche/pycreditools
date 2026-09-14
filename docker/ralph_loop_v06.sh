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
# Quatro rodadas de critica, por decisao do dono (14/09). Medido no #157: uma rodada de
# auditoria marca 3,1 a 5,5 no medidor e uma de implementacao ~0,7 — com 8 rodadas um unico
# ticket podia comer mais de um TERCO do teto semanal. E rodada tem retorno decrescente.
# Esgotadas as quatro SEM ACORDO, o ticket POUSA MESMO ASSIM com o que o implementador fez
# (ver land_ticket): o auditor tem poder de exigir, nao de vetar.
MAX_ROUNDS="${MAX_ROUNDS:-4}"                    # audit rounds per ticket before stopping
# Um cap so para os dois papeis media coisas diferentes com a mesma regua. O trabalho do
# auditor e intrinsecamente mais pesado — ele le o diff INTEIRO e cada arquivo alterado por
# completo, porque "diff esconde o que o codigo ao redor faz" — e na primeira rodada do
# #157 ele fechou em 173k contra 40k do implementador. 173k nao e auditor descuidado, e o
# tamanho da tarefa; rotaciona-lo ali jogava fora a memoria dos proprios achados a cada
# rodada. CONTEXT_CAP_TOKENS continua valendo como default comum para os dois.
CONTEXT_CAP_TOKENS="${CONTEXT_CAP_TOKENS:-150000}"
# DESLIGADOS por decisao do dono (14/09). Rotacionar sessao trocava um problema por outro:
# o par perdia a memoria da negociacao no meio dela, e quem paga isso e a qualidade da
# auditoria, nao a conta. Com o briefing tambem no system prompt (ver PROMPT_DIR/system_*),
# compactar deixou de ser perda de identidade. 0 = sem teto; qualquer numero religa.
CONTEXT_CAP_IMPL="${CONTEXT_CAP_IMPL:-0}"
CONTEXT_CAP_AUDIT="${CONTEXT_CAP_AUDIT:-0}"
RATE_LIMIT_BACKOFF_SECONDS="${RATE_LIMIT_BACKOFF_SECONDS:-1800}"
MERGE_METHOD="${MERGE_METHOD:---merge}"          # --merge | --squash | --rebase
LOG_DIR="${LOG_DIR:-/workspace/.ralph/logs/v06}"

# --- Janela de trabalho -----------------------------------------------------------
# O loop so trabalha dentro desta janela (hora local de WORK_WINDOW_TZ). Fora dela ele
# dorme ate a proxima abertura, checando entre turnos — nunca no meio de um. Deixe
# START e END iguais (ou vazios) para rodar 24h.
WORK_WINDOW_START="${WORK_WINDOW_START:-22:00}"
WORK_WINDOW_END="${WORK_WINDOW_END:-08:00}"
WORK_WINDOW_TZ="${WORK_WINDOW_TZ:-America/Sao_Paulo}"
# Toda data que o loop MOSTRA sai nesta zona. O container roda em UTC, entao um log dizia
# "dormindo ate 15/09 01:00" quando o correto era "hoje as 22:00": instante certo, leitura
# enganosa — e um operador que nao confia no relogio do log nao confia no resto.
# Os nomes de arquivo de log seguem em UTC (usam `date -u`), que e o que se quer num nome.
export TZ="$WORK_WINDOW_TZ"

# --- Teto de uso ------------------------------------------------------------------
# ISTO NAO E DINHEIRO. A conta roda por ASSINATURA (CLAUDE_CODE_OAUTH_TOKEN), entao nada
# aqui e cobrado — o que o loop gasta e COTA. Acontece que a unica grandeza de consumo
# observavel localmente e o `total_cost_usd` que o CLI devolve por turno: o preco que
# aqueles tokens teriam na API. E um MEDIDOR, nao uma fatura, e serve de freio porque sobe
# junto com a cota consumida.
# Calibre WEEKLY_BUDGET_USD empiricamente: compare o acumulado deste livro-caixa com o
# percentual real que o `/usage` mostra numa sessao interativa. Referencia medida: o turno
# de implementacao do ticket 1 marcou 11,10 neste medidor.
# O loop soma a janela movel de 7 dias e PARA (dormindo, nao morrendo) ao atingir
# BUDGET_STOP_PCT do teto — a janela movel se recupera sozinha com o passar dos dias.
WEEKLY_BUDGET_USD="${WEEKLY_BUDGET_USD:-150}"
BUDGET_STOP_PCT="${BUDGET_STOP_PCT:-80}"
# O periodo. A cota da assinatura reseta num INSTANTE FIXO da semana, nao numa janela
# movel — e a diferenca importa: logo depois de um reset voce tem cota cheia, mas uma
# soma movel de 7 dias ainda carrega os seis dias anteriores e te freia justamente quando
# ha espaco. Ancore no reset. "rolling" fica disponivel para quem nao souber o proprio.
BUDGET_PERIOD="${BUDGET_PERIOD:-fixed}"              # fixed | rolling
BUDGET_RESET_DOW="${BUDGET_RESET_DOW:-friday}"
BUDGET_RESET_HOUR="${BUDGET_RESET_HOUR:-03:00}"
BUDGET_TZ="${BUDGET_TZ:-America/Sao_Paulo}"
USAGE_LEDGER="${USAGE_LEDGER:-/workspace/.ralph/usage.tsv}"

# --- Notificacoes -----------------------------------------------------------------
# Nada aqui e urgente: e projeto pessoal, roda de madrugada, e uma notificacao "urgent"
# do ntfy toca como alarme e ja acordou o dono as 4h. Teto de prioridade: "default".
NTFY_PRIORITY_ALERT="${NTFY_PRIORITY_ALERT:-default}"
NTFY_PRIORITY_INFO="${NTFY_PRIORITY_INFO:-low}"
HEARTBEAT_SECONDS="${HEARTBEAT_SECONDS:-7200}"    # sinal de vida durante espera IMPREVISTA
# Tamanho da fatia de sono. Curto o bastante para reancorar no relogio de parede depois de
# um suspend, longo o bastante para nao acordar a toa. Configuravel tambem porque com 60s
# uma espera curta nunca chega a uma iteracao intermediaria — e era assim que o teste do
# heartbeat nao conseguia observar o heartbeat.
SLEEP_BITE_SECONDS="${SLEEP_BITE_SECONDS:-60}"

# --- Watchdog ---------------------------------------------------------------------
# Um turno pendurado nao morre e o `restart: on-failure` nao o alcanca; o teto o mata.
TURN_TIMEOUT_SECONDS="${TURN_TIMEOUT_SECONDS:-7200}"

# --- Ambiente Python ---------------------------------------------------------------
# NAO e o .venv-linux do host: aquele e construido pelo Python do host (3.14 no Fedora) e
# seu site-packages e ilegivel para o Python 3.11 do container, entao o gate falhava com
# ModuleNotFoundError em TODO ticket. Este vive no home do container (volume nomeado) e e
# criado pelo entrypoint com o interpretador que vai roda-lo.
VENV="${VENV:-/home/ralph/venv}"
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

notify_info()  { notify.sh "$1" "$2" "$NTFY_PRIORITY_INFO"  >/dev/null 2>&1 || true; }
notify_alert() { notify.sh "$1" "$2" "$NTFY_PRIORITY_ALERT" >/dev/null 2>&1 || true; }

# ---------------------------------------------------------------------------
# Esperar ate um INSTANTE, nao por uma DURACAO. Esta distincao custou 8 horas: o backoff
# calculava certo o instante do reset da cota e entregava a diferenca para `sleep`, que
# conta em CLOCK_MONOTONIC — relogio que CONGELA enquanto a maquina esta suspensa. O PC
# dormiu, a contagem parou junto, a cota resetou 01:51Z e o loop seguiu esperando ate as
# 09:39Z. Dormir em fatias curtas reconferindo `date +%s` e imune a isso: cada acordada
# reancora no relogio de parede, entao suspend so adia, nunca trava.
# Emite sinal de vida a cada HEARTBEAT_SECONDS — do celular, silencio e indistinguivel de
# morte, e essa ambiguidade era um defeito de projeto para quem so acompanha por push.
# ---------------------------------------------------------------------------
# $3 = "quiet" quando a espera e ESPERADA (a janela de trabalho do dono). Heartbeat existe
# para espera IMPREVISTA — cota estourada, teto de uso — em que o silencio nao se distingue
# de travamento. A janela e o oposto: o dono sabe que sao 15h e sabe que o loop dorme ate as
# 22h, entao um aviso a cada duas horas so interrompe o dia dele para informar o obvio.
sleep_until() {
    local target="$1" why="${2:-}" quiet="${3:-}" now last_beat bite left
    now=$(date +%s); last_beat="$now"
    while [ "$now" -lt "$target" ]; do
        left=$(( target - now ))
        bite="$SLEEP_BITE_SECONDS"; [ "$left" -lt "$bite" ] && bite="$left"
        sleep "$bite"
        now=$(date +%s)
        if [ -z "$quiet" ] && [ $(( now - last_beat )) -ge "$HEARTBEAT_SECONDS" ] && [ "$now" -lt "$target" ]; then
            notify_info "v0.6 — em espera" "$why Retomo por volta de $(date -d "@$target" +%H:%M) ($(( (target - now) / 60 )) min)."
            last_beat="$now"
        fi
    done
}

# ---------------------------------------------------------------------------
# Janela de trabalho. Pura, para os testes pinarem: $1 = agora "HH:MM", $2 = inicio,
# $3 = fim. A janela normal aqui ATRAVESSA a meia-noite (22:00 -> 08:00), entao o caso
# invertido e o principal, nao a excecao. Inicio igual ao fim (ou vazio) = 24 horas.
# ---------------------------------------------------------------------------
in_window() {
    local now="$1" start="$2" end="$3"
    [ -z "$start" ] || [ -z "$end" ] || [ "$start" = "$end" ] && return 0
    now=$((10#${now//:/})); start=$((10#${start//:/})); end=$((10#${end//:/}))
    if [ "$start" -lt "$end" ]; then
        [ "$now" -ge "$start" ] && [ "$now" -lt "$end" ]
    else
        [ "$now" -ge "$start" ] || [ "$now" -lt "$end" ]
    fi
}

now_in_window() { in_window "$(TZ="$WORK_WINDOW_TZ" date +%H:%M)" "$WORK_WINDOW_START" "$WORK_WINDOW_END"; }

next_window_open() {
    local t
    t=$(TZ="$WORK_WINDOW_TZ" date -d "today $WORK_WINDOW_START" +%s 2>/dev/null) || { date +%s; return; }
    [ "$t" -le "$(date +%s)" ] && t=$(TZ="$WORK_WINDOW_TZ" date -d "tomorrow $WORK_WINDOW_START" +%s)
    echo "$t"
}

# Chamado ANTES de cada turno, nunca no meio de um: um turno interrompido perderia o
# trabalho que ainda nao virou commit.
wait_for_window() {
    local target
    now_in_window && return 0
    target=$(next_window_open)
    log "fora da janela de trabalho ($WORK_WINDOW_START-$WORK_WINDOW_END $WORK_WINDOW_TZ) — dormindo ate $(date -d "@$target" +%d/%m\ %H:%M)"
    notify_info "v0.6 — fora da janela" "Pausando ate $(date -d "@$target" +%H:%M). O dia e seu; o loop volta a noite."
    sleep_until "$target" "Fora da janela de trabalho." quiet
    notify_info "v0.6 — janela aberta" "Retomando o trabalho."
}

# ---------------------------------------------------------------------------
# Livro-caixa do medidor de consumo (ver o bloco de config: e cota, nao dinheiro).
# Puras, para os testes pinarem.
# ---------------------------------------------------------------------------
record_usage() {
    local file="$1" cost
    cost=$(jq -r '.total_cost_usd // 0' "$file" 2>/dev/null) || cost=0
    mkdir -p "$(dirname "$USAGE_LEDGER")" 2>/dev/null || true
    printf '%s\t%s\n' "$(date +%s)" "${cost:-0}" >> "$USAGE_LEDGER" 2>/dev/null || true
}

spend_since() {   # $1 = epoch de corte, $2 = livro (default USAGE_LEDGER)
    awk -v c="$1" 'BEGIN{s=0} $1 >= c {s += $2} END{printf "%.2f", s}' "${2:-$USAGE_LEDGER}" 2>/dev/null || echo "0.00"
}

budget_ceiling() { awk -v b="$WEEKLY_BUDGET_USD" -v p="$BUDGET_STOP_PCT" 'BEGIN{printf "%.2f", b*p/100}'; }

# O inicio do periodo de cota corrente. Pura o suficiente para os testes pinarem: aceita
# "agora" por $NOW_EPOCH.
budget_period_start() {
    local now="${NOW_EPOCH:-$(date +%s)}" want i d dow cand
    [ "$BUDGET_PERIOD" = "rolling" ] && { echo $(( now - 604800 )); return; }
    want=$(printf '%s' "$BUDGET_RESET_DOW" | tr '[:upper:]' '[:lower:]')
    # Caminhar para tras dia a dia ate achar o dia do reset cujo horario ja passou. Feito
    # assim, e nao com `date -d "last friday"`, porque aquela forma NUMA SEXTA devolve a
    # sexta ANTERIOR — contaria uma semana inteira de gasto que a conta ja zerou de manha.
    for i in 0 1 2 3 4 5 6 7; do
        d=$(TZ="$BUDGET_TZ" date -d "@$(( now - i * 86400 ))" +%Y-%m-%d 2>/dev/null) || continue
        dow=$(TZ="$BUDGET_TZ" date -d "$d" +%A 2>/dev/null | tr '[:upper:]' '[:lower:]')
        [ "$dow" = "$want" ] || continue
        cand=$(TZ="$BUDGET_TZ" date -d "$d $BUDGET_RESET_HOUR" +%s 2>/dev/null) || continue
        [ "$cand" -le "$now" ] && { echo "$cand"; return; }
    done
    echo $(( now - 604800 ))
}

# Verdadeiro quando o periodo de cota corrente ja encostou no teto.
over_budget() {
    local spent ceiling
    spent=$(spend_since "$(budget_period_start)")
    ceiling=$(budget_ceiling)
    awk -v s="$spent" -v c="$ceiling" 'BEGIN{exit !(s >= c)}'
}

# Nao morre: dorme uma hora e reconfere. A janela e MOVEL, entao ela se recupera sozinha
# conforme os turnos antigos saem dos 7 dias — parar de vez exigiria o dono voltar.
wait_for_budget() {
    local spent ceiling
    local since next
    while over_budget; do
        since=$(budget_period_start); spent=$(spend_since "$since"); ceiling=$(budget_ceiling)
        if [ "$BUDGET_PERIOD" = "rolling" ]; then next=$(( $(date +%s) + 3600 ))
        else next=$(( since + 604800 )); fi
        log "teto de uso atingido: ${spent} de ${ceiling} desde $(date -d "@$since" '+%d/%m %H:%M') — dormindo ate $(date -d "@$next" '+%d/%m %H:%M')"
        notify_info "v0.6 — teto de uso" "Medidor em ${spent} dos ${ceiling} do periodo (${BUDGET_STOP_PCT}% de ${WEEKLY_BUDGET_USD}, desde $(date -d "@$since" '+%d/%m %H:%M')). Pausado ate o reset em $(date -d "@$next" '+%d/%m %H:%M')."
        sleep_until "$next" "Teto de uso do periodo atingido."
    done
}

# ---------------------------------------------------------------------------
# Text handed VERBATIM from one session to the other. A full implementer report or audit
# can run to tens of thousands of tokens, and it is pasted again on EVERY round — the two
# sessions end up paying for each other's prose instead of for the work. Keep the TAIL:
# the findings and the sentinel live at the end, the preamble does not matter to the other
# side. Pure, so docker/tests/test_ralph_v06.sh can pin it.
# ---------------------------------------------------------------------------
CROSS_TALK_CHARS="${CROSS_TALK_CHARS:-12000}"
clip() {
    local text="$1" n="${2:-$CROSS_TALK_CHARS}"
    if [ "${#text}" -le "$n" ]; then printf '%s' "$text"; return 0; fi
    printf '[... %s caracteres iniciais cortados pelo loop; o que importa (achados e sentinela) esta abaixo ...]\n%s' \
        "$(( ${#text} - n ))" "${text: -n}"
}

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
# O pacote de contexto: o que o loop consegue descobrir em bash, ele descobre em bash.
#
# Medido no turno de implementacao do #157: 32 dos 124 turnos internos foram orientacao
# ANTES da primeira escrita — em boa parte, um `gh issue view` por card. E o consumo de um
# turno e (turnos x contexto): 97,7% do input foi releitura do MESMO contexto a cada passo,
# 18,87M de cache_read contra 447k de conteudo novo. Entao todo turno interno economizado
# cedo se paga em todos os turnos seguintes.
#
# Nada aqui exige modelo: sao chamadas de gh e git. O agente le UM arquivo em vez de
# descobrir a mesma coisa conversando.
# ---------------------------------------------------------------------------
build_context_pack() {
    # Declaracoes separadas de proposito: sob `set -u`, um unico `local a=$1 b=${a}` cria
    # TODOS os nomes como nao-associados antes de atribuir, e o ${a} da segunda explode.
    local n="$1"
    local pack="$LOG_DIR/pack_${n}.md"
    local body b
    body=$(gh issue view "$n" --repo "$REPO" --json body -q .body 2>/dev/null)
    {
        printf '# Contexto pre-coletado do ticket #%s\n\n' "$n"
        printf 'Montado pelo loop com `gh` e `git`, sem custo de modelo. NAO refaca o que ja\n'
        printf 'esta aqui — cada busca sua e paga de novo em todo turno seguinte.\n\n'
        printf -- '## O card, com os comentarios (a resolucao mora nos comentarios)\n\n'
        gh issue view "$n" --repo "$REPO" --comments 2>/dev/null
        printf '\n\n## Bloqueadores declarados, e o estado REAL de cada um\n\n'
        for b in $(parse_blockers "$body"); do
            gh issue view "$b" --repo "$REPO" --json number,title,state \
                -q '"- #\(.number) [\(.state)] \(.title)"' 2>/dev/null
        done
        printf '\n(Fechado no tracker nao e entregue na arvore: confirme no codigo o que voce for usar.)\n'
        printf '\n## Os ultimos 25 commits da base (%s)\n\n' "origin/$BASE_BRANCH"
        git log --oneline "origin/$BASE_BRANCH" -25 2>/dev/null
        printf '\n## Portao de artefato: ADRs prometidos que ainda faltam\n\n'
        python3 scripts/check_artifact_gate.py 2>&1 | tail -40 || true
    } > "$pack" 2>/dev/null
    printf '%s' "$pack"
}

# ---------------------------------------------------------------------------
# Prompt assembly. Templates live in the bind-mounted tree, so they can be edited
# without rebuilding the image.
# ---------------------------------------------------------------------------
render_prompt() {
    local file="$1" n="$2" round="${3:-1}"
    sed -e "s|{{REPO}}|$REPO|g" -e "s|{{ISSUE}}|$n|g" -e "s|{{BRANCH}}|${WORK_BRANCH:-}|g" \
        -e "s|{{BASE}}|origin/$BASE_BRANCH|g" -e "s|{{ROUND}}|$round|g" \
        -e "s|{{MAX_ROUNDS}}|$MAX_ROUNDS|g" -e "s|{{VENV}}|$VENV|g" \
        -e "s|{{PACK}}|${CONTEXT_PACK:-}|g" "$PROMPT_DIR/$file"
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

# $1 = contexto medido, $2 = papel (impl|audit). Pura, para os testes pinarem.
cap_for_role() {
    [ "${1:-}" = "audit" ] && echo "$CONTEXT_CAP_AUDIT" || echo "$CONTEXT_CAP_IMPL"
}

over_context_cap() {
    local ctx="${1:-0}" cap
    cap=$(cap_for_role "${2:-impl}")
    [ "$cap" -gt 0 ] || return 1      # 0 = sem teto
    [ "$ctx" -gt "$cap" ]
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

    # `timeout` e o watchdog: um turno pendurado nao morre sozinho e o `restart:
    # on-failure` do compose nunca o alcanca, porque o processo continua vivo.
    # O papel, as regras inegociaveis e o vocabulario de sentinela vao no SYSTEM prompt,
    # nao so no prompt do turno: system prompt sobrevive a compactacao. Foi perder o
    # briefing numa sessao reiniciada que fez o implementador inventar sentinela e dar
    # push, as duas coisas proibidas no texto que ele nao tinha mais.
    local sys="$PROMPT_DIR/system_${role}.md"
    local -a cmd=(timeout "$TURN_TIMEOUT_SECONDS"
                  claude --print "$prompt" --model "$MODEL" --effort "$EFFORT"
                  --output-format json --dangerously-skip-permissions)
    [ -f "$sys" ] && cmd+=(--append-system-prompt "$(cat "$sys")")
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
    [ "$role" = "audit" ] && LAST_AUDIT_LOG="$LAST_OUTPUT_FILE" || LAST_IMPL_LOG="$LAST_OUTPUT_FILE"
    record_usage "$LAST_OUTPUT_FILE"

    if [ -z "$LAST_STATUS" ]; then
        # Prefer the CLI's STRUCTURED 429 over text-matching: grepping the raw JSON for
        # "429" gave false positives (it matched "429" inside token counts) and the
        # wording varies ("session limit" / "usage limit" / "5-hour limit reached").
        local api_err
        api_err=$(jq -r '.api_error_status // empty' "$LAST_OUTPUT_FILE" 2>/dev/null)
        if [ "$api_err" = "429" ] || is_rate_limited_file "$LAST_OUTPUT_FILE"; then
            LAST_STATUS="RATE_LIMITED"
        elif [ "$exit_code" -eq 124 ]; then
            LAST_STATUS="TIMEOUT"
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
    local role="$1" prompt="$2" var="$3" sid backoff target
    eval "sid=\${$var:-}"
    # As duas politicas do dono, checadas ENTRE turnos: a janela de trabalho e o teto de
    # uso. Nunca no meio de um turno — interromper perderia o que ainda nao virou commit.
    wait_for_window
    wait_for_budget
    run_claude_turn "$role" "$prompt" "$sid"
    while [ "$LAST_STATUS" = "RATE_LIMITED" ]; do
        backoff=$(rate_limit_backoff_seconds)
        # O instante-alvo, nao a duracao — ver sleep_until.
        target=$(( $(date +%s) + backoff ))
        notify_info "v0.6 — limite de uso" "Cota atingida na #$ISSUE ($role). Retomo por volta de $(date -d "@$target" +%H:%M), um minuto apos o reset informado."
        log "#$ISSUE $role rate-limited — waiting until $(date -d "@$target" +%H:%M:%S) (${backoff}s)"
        sleep_until "$target" "Cota atingida na #$ISSUE."
        wait_for_window
        run_claude_turn "$role" "$prompt" "${LAST_SESSION_ID:-$sid}"
    done
    [ -n "${LAST_SESSION_ID:-}" ] && eval "$var=\"\$LAST_SESSION_ID\""
    if over_context_cap "${LAST_CTX_TOKENS:-0}" "$role"; then
        notify_info "v0.6 — sessao rotacionada" "A sessao $role da #$ISSUE passou de $(cap_for_role "$role") tokens de contexto (${LAST_CTX_TOKENS}). A proxima rodada comeca fresca, com o briefing inteiro; o trabalho esta nos commits."
        log "#$ISSUE $role over context cap (${LAST_CTX_TOKENS} > $(cap_for_role "$role")) — rotating session"
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
    # $VENV, nunca o .venv-linux do host: aquele e de outro interpretador (3.14 contra os
    # 3.11 daqui) e o gate morria com ModuleNotFoundError em todo ticket.
    [ -x "$VENV/bin/python" ] && py="$VENV/bin/python"
    log "verifying #$ISSUE (pytest + ruff) before accepting agreement..."
    "$py" -m pytest tests --ignore=tests/studio -q > "$vlog" 2>&1 || pt=$?
    if [ -x "$VENV/bin/ruff" ]; then
        "$VENV/bin/ruff" check src/pycreditools/engine tests/engine >> "$vlog" 2>&1 || rf=$?
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
        notify_alert "v0.6 — falha no push" "A #$n foi implementada e auditada, mas o push falhou. Parando."
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
    if [ -n "${DISSENT:-}" ]; then
        gh pr comment "$pr" --repo "$REPO" \
            --body "$(printf 'Pousado SEM acordo do par (%s). Pela regra da casa, o auditor exige mas nao veta: prevalece o que o implementador fez, e os achados em aberto estao registrados na issue #%s para voce julgar. O gate do loop (pytest + ruff) foi re-executado e esta verde — isso nao se negocia.' "$DISSENT" "$n")" \
            >/dev/null 2>&1 || true
    else
        gh pr comment "$pr" --repo "$REPO" \
            --body "Par implementador x auditor em acordo apos ${rounds} rodada(s). Gate re-executado pelo loop: verde." \
            >/dev/null 2>&1 || true
    fi
    if gh pr merge "$pr" --repo "$REPO" $MERGE_METHOD --delete-branch >/dev/null 2>&1; then
        log "PR #$pr merged into $BASE_BRANCH"
    else
        notify_alert "v0.6 — merge falhou" "PR #$pr (issue #$n) nao mergeou. A branch $WORK_BRANCH esta no remoto. Parando."
        log "merge failed for PR #$pr"
        return 1
    fi
    # A merge into release/v0.6 is not on the default branch, so GitHub never closes the
    # issue by itself — close it here or the queue re-picks work that is already done.
    # `|| true` fazia uma falha de API aqui virar tracker mentindo em silencio: confira o
    # estado depois de fechar e avise se a issue continuar aberta.
    gh issue close "$n" --repo "$REPO" --reason completed >/dev/null 2>&1 || true
    gh issue edit "$n" --repo "$REPO" --remove-label "$QUEUE_LABEL" >/dev/null 2>&1 || true
    if [ "$(gh issue view "$n" --repo "$REPO" --json state -q .state 2>/dev/null)" != "CLOSED" ]; then
        log "WARN: #$n continua aberta depois do merge do PR #$pr"
        notify_alert "v0.6 — issue #$n nao fechou" "O PR #$pr mergeou, mas a issue #$n continua aberta. Feche na mao para a fila nao repescar trabalho pronto."
    fi
    git checkout --quiet "$BASE_BRANCH" 2>/dev/null \
        || git checkout --quiet -B "$BASE_BRANCH" "origin/$BASE_BRANCH"
    git pull --quiet --ff-only origin "$BASE_BRANCH" 2>/dev/null || true
    if [ -n "${DISSENT:-}" ]; then
        notify_info "#$n concluida (sem acordo)" "PR #$pr mergeado apos ${rounds} rodada(s). O par nao fechou acordo — prevaleceu o implementador e os achados em aberto estao na issue. Gate verde."
    else
        notify_info "#$n concluida" "PR #$pr mergeado em $BASE_BRANCH apos ${rounds} rodada(s) de auditoria. Issue fechada. Seguindo para o proximo ticket."
    fi
    return 0
}

issue_note() {
    local n="$1" text="$2"
    gh issue comment "$n" --repo "$REPO" --body "$(printf '%s' "$text" | head -c 60000)" \
        >/dev/null 2>&1 || true
}

# ---------------------------------------------------------------------------
# O vocabulario de sentinelas de cada papel, e a segunda chance.
# Uma sentinela fora do vocabulario parava o loop como se fosse falha — foi assim que a
# rodada 1 do #157 morreu, com um "STATUS: CHANGES_MADE" que so queria dizer DONE. Perder
# o trabalho de uma noite por uma palavra e desproporcional: peca a palavra certa.
# Puras (as duas primeiras), para os testes pinarem.
# ---------------------------------------------------------------------------
valid_sentinel() {
    case "$1:$2" in
        impl:DONE|impl:BLOCKED|impl:WRONG_TICKET|impl:ERROR) return 0 ;;
        audit:AGREED|audit:CHANGES_REQUESTED|audit:ESCALATE) return 0 ;;
        *) return 1 ;;
    esac
}

sentinel_vocabulary() {
    if [ "$1" = "audit" ]; then
        echo "VERDICT: AGREED | VERDICT: CHANGES_REQUESTED | VERDICT: ESCALATE"
    else
        echo "STATUS: DONE | STATUS: BLOCKED | STATUS: WRONG_TICKET | STATUS: ERROR"
    fi
}

ask_valid_sentinel() {
    local role="$1" var="IMPL_SESSION" key="STATUS"
    [ "$role" = "audit" ] && { var="AUDIT_SESSION"; key="VERDICT"; }
    valid_sentinel "$role" "${LAST_STATUS:-}" && return 0
    # Falhas de infraestrutura sao tratadas noutro lugar; aqui so vocabulario.
    case "${LAST_STATUS:-}" in RATE_LIMITED|TIMEOUT|CLI_ERROR) return 0 ;; esac
    log "#$ISSUE $role terminou com sentinela invalida ('${LAST_STATUS:-vazia}') — pedindo a correta"
    turn_with_retries "$role" "$(printf 'Your last message ended with `%s: %s`, which is not one of the sentinels this loop understands. Nothing you did is lost and nothing needs redoing — the loop only needs the right word for the state you are already in.\n\nReply with a one-line summary and then exactly one of:\n\n%s\n\nNothing else.' \
        "$key" "${LAST_STATUS:-<nenhuma>}" "$(sentinel_vocabulary "$role")")" "$var"
}

# ---------------------------------------------------------------------------
# Estado da negociacao, em disco.
# Ele so existia em memoria, entao TODO restart do container fazia o par recomecar o ticket
# na rodada 1 — medido no #157, que rodou o implementador tres vezes do zero (09:41, 10:15,
# 10:26) porque o container foi recriado entre elas. Os commits sobreviviam; a negociacao,
# nao. Com a maquina desligando e a janela de trabalho cortando a noite, restart deixou de
# ser excecao, e perder a rodada e perder dinheiro de cota.
# ---------------------------------------------------------------------------
state_file() { echo "${LOG_DIR}/state_${1}.env"; }

save_ticket_state() {
    local n="$1"
    { printf 'ROUND=%s\n' "${2:-0}"
      printf 'IMPL_SESSION=%s\n' "${IMPL_SESSION:-}"
      printf 'AUDIT_SESSION=%s\n' "${AUDIT_SESSION:-}"
      printf 'LAST_AUDIT_LOG=%s\n' "${LAST_AUDIT_LOG:-}"
      printf 'LAST_IMPL_LOG=%s\n' "${LAST_IMPL_LOG:-}"
    } > "$(state_file "$n")" 2>/dev/null || true
}

clear_ticket_state() { rm -f "$(state_file "$1")" 2>/dev/null || true; }

# Devolve o texto do resultado de um turno gravado, para reconstruir a conversa sem modelo.
result_of_log() { [ -s "${1:-}" ] && jq -r '.result // empty' "$1" 2>/dev/null || true; }

# ---------------------------------------------------------------------------
# One ticket, end to end: implement -> audit -> argue -> land. Returns 0 when the ticket
# landed, 1 when the loop must stop for a human.
# ---------------------------------------------------------------------------
run_ticket() {
    local n="$1" round=0 impl_report audit_findings audit_prompt fix_prompt
    IMPL_SESSION=""; AUDIT_SESSION=""; DISSENT=""
    LAST_AUDIT_LOG=""; LAST_IMPL_LOG=""
    ensure_branch_for_issue "$n"

    # Retomar a negociacao, se um restart a interrompeu. A rodada 1 (a implementacao) so e
    # refeita quando nao ha estado — o trabalho ja esta nos commits e refaze-lo e pagar duas
    # vezes pela mesma coisa.
    local resumed=0
    if [ -s "$(state_file "$n")" ]; then
        # shellcheck disable=SC1090
        . "$(state_file "$n")"
        round="${ROUND:-0}"
        impl_report=$(result_of_log "${LAST_IMPL_LOG:-}")
        audit_findings=$(result_of_log "${LAST_AUDIT_LOG:-}")
        if [ "$round" -gt 0 ] && [ -n "$impl_report" ]; then
            resumed=1
            log "#$n: retomando a negociacao na rodada $round (estado em disco)"
            notify_info "v0.6 — retomando a #$n" "Um restart interrompeu o ticket na rodada $round. Retomando dali, sem refazer o que ja esta commitado."
        else
            round=0
        fi
    fi

    CONTEXT_PACK=$(build_context_pack "$n")
    log "pacote de contexto: $CONTEXT_PACK ($(wc -l < "$CONTEXT_PACK" 2>/dev/null || echo 0) linhas)"

    if [ "$resumed" -eq 0 ]; then
        turn_with_retries impl "$(render_prompt v06_implementer.md "$n" 1)" IMPL_SESSION
        impl_report="$LAST_RESULT_TEXT"
        ask_valid_sentinel impl
    else
        LAST_STATUS=DONE   # o turno que produziu este relatorio ja tinha terminado bem
    fi

    case "$LAST_STATUS" in
        DONE) ;;
        WRONG_TICKET)
            issue_note "$n" "$(printf 'O par headless parou antes de implementar: o ticket nao parece ser o trabalho certo agora.\n\n%s' "$impl_report")"
            gh issue edit "$n" --repo "$REPO" --add-label "needs-triage" >/dev/null 2>&1 || true
            notify_alert "v0.6 — ticket errado (#$n)" "O implementador sustenta que a #$n nao e o trabalho certo agora. Comentei na issue com a evidencia e parei."
            return 1 ;;
        BLOCKED)
            issue_note "$n" "$(printf 'O par headless parou: BLOCKED.\n\n%s' "$impl_report")"
            gh issue edit "$n" --repo "$REPO" --add-label "needs-info" >/dev/null 2>&1 || true
            notify_alert "v0.6 — issue bloqueada (#$n)" "Precisa de uma decisao sua. Comentei na issue. Log: $LAST_OUTPUT_FILE"
            return 1 ;;
        *)
            notify_alert "v0.6 — ERRO na #$n" "Implementador terminou com STATUS=$LAST_STATUS. Log: $LAST_OUTPUT_FILE"
            return 1 ;;
    esac

    while [ "$round" -lt "$MAX_ROUNDS" ]; do
        round=$((round + 1))
        save_ticket_state "$n" "$round"
        if [ -n "$AUDIT_SESSION" ] && [ "$round" -gt 1 ]; then
            audit_prompt=$(printf 'Audit round %s of %s on #%s. The implementer answered your findings:\n\n--- IMPLEMENTER RESPONSE ---\n%s\n--- END ---\n\nRe-read `git diff origin/%s...HEAD` (it moved), re-run the gate yourself, and check each of your earlier findings: fixed, worked around, or correctly argued down. Raise anything new the fix introduced. End with exactly one VERDICT line.' \
                "$round" "$MAX_ROUNDS" "$n" "$(clip "$impl_report")" "$BASE_BRANCH")
        else
            audit_prompt=$(render_prompt v06_auditor.md "$n" "$round")
            if [ "$round" -gt 1 ]; then
                # Sem os achados da rodada anterior, um auditor fresco so recebia a
                # ALEGACAO de quem ele auditou sobre o que corrigiu — e nao tinha como
                # distinguir "consertado" de "contornado", que e exatamente a distincao
                # que o Step 2 manda ele fazer. Mesmo buraco que o prompt de correcao do
                # implementador tinha; este e o lado simetrico.
                audit_prompt=$(printf '%s\n\n## Continuation — voce nao e a mesma sessao, e os achados abaixo sao SEUS\n\nEsta sessao de auditoria e nova (a anterior estourou o teto de contexto), mas o trabalho esta na rodada %s. Trate os achados abaixo como seus proprios, nao como sugestao: para cada um, decida por EVIDENCIA se foi consertado, CONTORNADO, ou corretamente rebatido — a alegacao do implementador e reivindicacao, nao prova.\n\n--- SEUS ACHADOS DA RODADA ANTERIOR ---\n%s\n--- FIM ---\n\nE a resposta do implementador a eles:\n\n--- RESPOSTA DO IMPLEMENTADOR ---\n%s\n--- FIM ---\n' \
                    "$audit_prompt" "$round" "$(clip "$audit_findings")" "$(clip "$impl_report")")
            fi
        fi
        turn_with_retries audit "$audit_prompt" AUDIT_SESSION
        audit_findings="$LAST_RESULT_TEXT"
        ask_valid_sentinel audit

        case "$LAST_STATUS" in
            AGREED)
                log "#$n: pair agreed after $round round(s)"
                clear_ticket_state "$n"
                if ! verify_turn; then
                    issue_note "$n" "O par declarou acordo na #$n, mas o gate do loop (pytest/ruff) falhou. Nada foi empurrado. Veja \`.ralph/logs/v06/verify_${n}.log\`."
                    notify_alert "v0.6 — verificacao falhou (#$n)" "Par em acordo mas pytest/ruff vermelho. NADA foi empurrado. Veja .ralph/logs/v06/verify_${n}.log"
                    return 1
                fi
                land_ticket "$n" "$round" || return 1
                return 0 ;;
            CHANGES_REQUESTED)
                log "#$n: audit round $round requested changes"
                fix_prompt=$(printf 'The auditor reviewed your work on #%s and asked for changes (round %s of %s). Their findings, verbatim:\n\n--- AUDIT ---\n%s\n--- END ---\n\nFor each finding: fix it, or argue it down with evidence (file:line, a command and its output) if the auditor is wrong — do not cave to a wrong finding and do not hand-wave a right one. NITs may be ignored. Re-run the gate, commit, then report what you changed and what you pushed back on.\n\nEnd your final message with exactly ONE sentinel line, one of: %s' \
                    "$n" "$round" "$MAX_ROUNDS" "$(clip "$audit_findings")" "$(sentinel_vocabulary impl)")
                # Sessao rotacionada = sessao SEM MEMORIA do briefing. Na rodada 1 do
                # #157 este prompt era so a lista de achados, e a sessao fresca que o
                # recebeu inventou uma sentinela ("STATUS: CHANGES_MADE", que parou o
                # loop) e deu `git push` — as duas coisas proibidas no briefing que ela
                # nao tinha. Sem sessao para retomar, o prompt carrega o briefing inteiro.
                if [ -z "${IMPL_SESSION:-}" ]; then
                    fix_prompt=$(printf '%s\n\n## Briefing completo (esta sessao e nova)\n\nA sessao anterior foi rotacionada por tamanho de contexto, entao voce NAO tem memoria do briefing original. Ele esta abaixo na integra. O trabalho ja feito esta nos commits da branch: leia `git log --oneline %s..HEAD` e `git diff %s...HEAD` antes de mexer em qualquer coisa.\n\n%s' \\
                        "$fix_prompt" "origin/$BASE_BRANCH" "origin/$BASE_BRANCH" "$(render_prompt v06_implementer.md "$n" "$round")")
                fi
                turn_with_retries impl "$fix_prompt" IMPL_SESSION
                impl_report="$LAST_RESULT_TEXT"
                ask_valid_sentinel impl
                if [ "$LAST_STATUS" != "DONE" ]; then
                    issue_note "$n" "$(printf 'O implementador parou na rodada %s com STATUS=%s.\n\n%s' "$round" "$LAST_STATUS" "$impl_report")"
                    notify_alert "v0.6 — implementador parou (#$n)" "STATUS=$LAST_STATUS na rodada $round. Log: $LAST_OUTPUT_FILE"
                    return 1
                fi ;;
            ESCALATE)
                # Empate nao para mais o loop. Regra do dono: o auditor pode EXIGIR revisao,
                # cobertura e documentacao, mas nao mandar — se nunca chegam a acordo, vale o
                # que o implementador fez. As duas posicoes ficam registradas na issue, e o
                # gate do loop continua sendo inegociavel.
                log "#$n: empate na rodada $round — prevalece o trabalho do implementador"
                clear_ticket_state "$n"
                issue_note "$n" "$(printf 'O par empatou numa decisao de projeto na rodada %s. Pela regra da casa, prevalece o que o implementador fez; as duas posicoes ficam aqui para leitura.\n\n### Posicao do auditor\n\n%s\n\n### Posicao do implementador\n\n%s' "$round" "$audit_findings" "$impl_report")"
                DISSENT="empate de projeto na rodada $round"
                if ! verify_turn; then
                    issue_note "$n" "O empate seria resolvido a favor do implementador, mas o gate do loop (pytest/ruff) falhou. Nada foi empurrado."
                    notify_alert "v0.6 — gate vermelho na #$n" "Empate resolvido a favor do implementador, mas pytest/ruff falhou. NADA foi empurrado."
                    return 1
                fi
                land_ticket "$n" "$round" || return 1
                return 0 ;;
            *)
                notify_alert "v0.6 — ERRO na auditoria da #$n" "Auditor terminou com VERDICT=$LAST_STATUS. Log: $LAST_OUTPUT_FILE"
                return 1 ;;
        esac
    done

    # Esgotadas as rodadas sem acordo: PREVALECE O IMPLEMENTADOR. O auditor exige, nao veta.
    # O que nao cede e o gate — esse o loop roda sozinho e nao negocia.
    log "#$n: sem acordo em $MAX_ROUNDS rodadas — prevalece o trabalho do implementador"
    clear_ticket_state "$n"
    issue_note "$n" "$(printf 'O par nao chegou a acordo em %s rodadas de critica. Pela regra da casa, prevalece o que o implementador fez — o auditor tem poder de exigir revisao, cobertura e documentacao, nao de vetar. Os achados em aberto ficam abaixo para voce julgar depois.\n\n### Achados que o auditor manteve\n\n%s\n\n### Resposta do implementador\n\n%s' "$MAX_ROUNDS" "$audit_findings" "$impl_report")"
    DISSENT="$MAX_ROUNDS rodadas sem acordo"
    if ! verify_turn; then
        issue_note "$n" "As rodadas se esgotaram a favor do implementador, mas o gate do loop (pytest/ruff) falhou. Nada foi empurrado."
        notify_alert "v0.6 — gate vermelho na #$n" "Rodadas esgotadas, mas pytest/ruff falhou. NADA foi empurrado."
        return 1
    fi
    land_ticket "$n" "$round" || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Main loop. Sourced with RALPH_V06_LIB_ONLY=1, the file defines the functions and stops
# here — that is how docker/tests/test_ralph_v06.sh pins the pure helpers.
# ---------------------------------------------------------------------------
main() {
log "starting — model=$MODEL effort=$EFFORT rounds<=$MAX_ROUNDS ctx_cap=$CONTEXT_CAP_TOKENS base=$BASE_BRANCH"
notify_info "v0.6 — loop iniciado" "Par implementador x auditor no ar. Modelo $MODEL (effort $EFFORT), ate $MAX_ROUNDS rodadas por ticket, PRs contra $BASE_BRANCH."

while true; do
    ISSUE=$(next_issue)
    if [ -z "$ISSUE" ]; then
        remaining=$(count_open_queue)
        if [ "$remaining" -gt 1 ]; then
            notify_alert "v0.6 — fila travada" "Restam $remaining issue(s) com $QUEUE_LABEL, todas bloqueadas por dependencia aberta. Veja o grafo de Blocked by."
            log "$remaining queue issue(s) left but all blocked — stopping for a human."
        else
            notify_info "v0.6 — fila vazia" "Nenhum ticket acionavel restante. Revise $BASE_BRANCH."
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
