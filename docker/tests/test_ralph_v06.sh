#!/usr/bin/env bash
# Pins the pure helpers of docker/ralph_loop_v06.sh. Run it inside the loop image (it
# needs jq and GNU date):
#
#   docker compose run --rm --entrypoint bash ralph_v06 docker/tests/test_ralph_v06.sh
#
# Every one of these guards a failure mode that actually cost time: the phantom blocker
# that deadlocked the v2 queue, the blind 30-minute rate-limit poll that burned ~4.5h,
# and the aggregate `usage` block that reads 400k+ when the live context is near 100k.
set -uo pipefail

RALPH_V06_LIB_ONLY=1
export RALPH_V06_LIB_ONLY
# shellcheck source=../ralph_loop_v06.sh
. "$(dirname "$0")/../ralph_loop_v06.sh"

PASS=0
FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok   — $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL — $1"; echo "         expected: [$2]"; echo "         got:      [$3]"; }
eq()   { [ "$2" = "$3" ] && ok "$1" || bad "$1" "$2" "$3"; }

echo "parse_blockers"
BODY_NONE=$'## Blocked by\n\nNone — can start immediately.\n'
BODY_TWO=$'## What to build\n\n- #999 is only prose here\n\n## Blocked by\n\n- #158\n- #161\n'
# The phantom-blocker case: the number lives inside a blocker's TITLE, not at the start.
BODY_TITLE=$'## Blocked by\n\n- #160 — Bancada tracer #1 e o portão #7\n'
eq "no blockers declared"        ""            "$(parse_blockers "$BODY_NONE")"
eq "two leading refs"            $'158\n161'   "$(parse_blockers "$BODY_TWO")"
eq "numbers inside a title are not blockers" "160" "$(parse_blockers "$BODY_TITLE")"

echo "sentinel_of"
eq "impl sentinel"               "DONE"    "$(sentinel_of impl  'blah\nSTATUS: DONE')"
eq "audit sentinel"              "AGREED"  "$(sentinel_of audit 'blah\nVERDICT: AGREED')"
eq "last sentinel wins"          "CHANGES_REQUESTED" \
   "$(sentinel_of audit 'I nearly wrote VERDICT: AGREED but then
VERDICT: CHANGES_REQUESTED')"
eq "audit ignores a STATUS line" ""        "$(sentinel_of audit 'STATUS: DONE')"
eq "impl ignores a VERDICT line" ""        "$(sentinel_of impl  'VERDICT: AGREED')"

echo "rate_limit_backoff_seconds"
RATE_LIMIT_BACKOFF_SECONDS=1800
MAX_SLEEP_SECONDS=21600
# 2026-09-12 09:00:00 UTC. A session window is five hours, so a realistic hint lands
# inside the day and inside the max sleep.
NOW_EPOCH=$(date -u -d '2026-09-12 09:00:00' +%s)
export NOW_EPOCH
eq "resets 1:30pm UTC — same day, 1 min past"   "$((4*3600 + 30*60 + 60))"    "$(rate_limit_backoff_seconds "You've hit your session limit · resets 1:30pm (UTC)")"
eq "resets 11am, no meridiem, no tz"            "$((2*3600 + 60))"    "$(rate_limit_backoff_seconds 'usage limit reached · resets 11am')"
eq "5-hour limit wording"                       "$((5*3600 + 60))"    "$(rate_limit_backoff_seconds 'Claude usage limit reached · your limit resets 2pm (UTC)')"
eq "unparseable wording falls back"             "1800"    "$(rate_limit_backoff_seconds 'you have hit your limit, come back later')"
eq "empty text falls back"                      "1800"    "$(rate_limit_backoff_seconds '')"
# A reset already past today rolls forward a day — never a negative sleep — and then
# exceeds the max sleep, so it is slept in one MAX_SLEEP bite.
eq "a past reset rolls forward, never negative" "21600"    "$(rate_limit_backoff_seconds 'resets 8am (UTC)')"
# The bite, not the old 30-min blind poll: a far reset sleeps MAX_SLEEP and re-parses.
eq "a reset beyond MAX_SLEEP sleeps one bite"   "21600"    "$(rate_limit_backoff_seconds 'resets 10:30pm (UTC)')"
eq "MAX_SLEEP bite is never the fixed fallback" "21600"    "$(MAX_SLEEP_SECONDS=21600 rate_limit_backoff_seconds 'resets 11pm (UTC)')"
# The +60 grace is additive, so a reset ten seconds out sleeps 70s: the sleep can never
# be shorter than the grace, which is what the floor exists to guarantee.
eq "a reset seconds away sleeps the grace"       "70"    "$(NOW_EPOCH=$(date -u -d '2026-09-12 08:59:50' +%s) rate_limit_backoff_seconds 'resets 9am (UTC)')"

echo "is_rate_limited_file"
tmp=$(mktemp -d)
printf '{"result":"Claude usage limit reached"}' > "$tmp/a.json"; : > "$tmp/a.stderr"
printf '{"result":"all good, 4290 tokens"}'      > "$tmp/b.json"; : > "$tmp/b.stderr"
if is_rate_limited_file "$tmp/a.json"; then ok "usage limit detected"; else bad "usage limit detected" "0" "1"; fi
if is_rate_limited_file "$tmp/b.json"; then bad "429 digits in a token count are NOT a rate limit" "1" "0"; else ok "429 digits in a token count are NOT a rate limit"; fi

echo "session_context_tokens"
TRANSCRIPT_DIR="$tmp/transcripts"
export TRANSCRIPT_DIR
mkdir -p "$TRANSCRIPT_DIR"
{
  printf '{"type":"assistant","message":{"usage":{"input_tokens":5,"cache_creation_input_tokens":1000,"cache_read_input_tokens":50000,"output_tokens":100}}}\n'
  printf '{"type":"user","message":{"content":"x"}}\n'
  printf '{"type":"assistant","message":{"usage":{"input_tokens":3,"cache_creation_input_tokens":2000,"cache_read_input_tokens":105868,"output_tokens":386}}}\n'
} > "$TRANSCRIPT_DIR/sid-1.jsonl"
eq "reads the LAST assistant usage, not the sum" "108257" "$(session_context_tokens sid-1)"
eq "unknown session is 0"                        "0"      "$(session_context_tokens sid-nope)"
eq "empty session id is 0"                       "0"      "$(session_context_tokens '')"

echo "over_context_cap"
# Pinned locally so the test states the boundary it checks instead of inheriting it
# from the environment — but it must track the script's own default, or the pair
# below stops testing the boundary that actually ships.
CONTEXT_CAP_TOKENS=150000
if over_context_cap 149999; then bad "under the cap passes" "1" "0"; else ok "under the cap passes"; fi
if over_context_cap 150001; then ok "over the cap trips"; else bad "over the cap trips" "0" "1"; fi
if over_context_cap 0;      then bad "an unknown context (0) never trips" "1" "0"; else ok "an unknown context (0) never trips"; fi

echo "slugify"
# Accents fold to ASCII, they do not mangle: a bracket class turned "ões" into "aaes" and
# iconv//TRANSLIT under the C locale turned it into a dash.
eq "pt-BR accents fold to ASCII" "adrs-das-decisoes-congeladas"    "$(slugify 'ADRs das decisões congeladas')"
eq "a real card title"           "semente-tolerancia-e-rodadas-pareadas"    "$(slugify 'Semente, tolerância e rodadas pareadas')"
eq "no leading or trailing dashes"      "choose-grid-criterion-by" \
   "$(slugify '`choose(grid, criterion=, by=)`')"

echo "clip"
# Cross-session text is pasted again on every round, so it is capped — and the TAIL is what
# is kept, because the findings and the sentinel live at the end of a report.
eq "short text passes through untouched" "curto" "$(CROSS_TALK_CHARS=100 clip 'curto')"
eq "long text keeps the tail"            "FIM"   "$(CROSS_TALK_CHARS=3 clip 'preambulo inutil FIM' | tail -1)"
case "$(CROSS_TALK_CHARS=3 clip 'preambulo inutil FIM')" in
    *"cortados pelo loop"*) ok "a cut says so, so neither agent reads a truncation as the whole report" ;;
    *) bad "a cut says so" "a marker line" "no marker" ;;
esac

echo "in_window"
# A janela normal deste projeto ATRAVESSA a meia-noite (22:00 -> 08:00), entao o caso
# invertido e o principal, nao a excecao — foi o que a primeira versao errou.
yes_() { if in_window "$2" "$3" "$4"; then ok "$1"; else bad "$1" "dentro" "fora"; fi; }
no_()  { if in_window "$2" "$3" "$4"; then bad "$1" "fora" "dentro"; else ok "$1"; fi; }
yes_ "23:30 esta dentro de 22:00-08:00"        "23:30" "22:00" "08:00"
yes_ "03:00 (depois da meia-noite) esta dentro" "03:00" "22:00" "08:00"
yes_ "22:00 em ponto abre a janela"             "22:00" "22:00" "08:00"
no_  "08:00 em ponto ja fechou"                 "08:00" "22:00" "08:00"
no_  "14:00 esta fora"                          "14:00" "22:00" "08:00"
yes_ "janela que nao atravessa: 10:00 em 09-18" "10:00" "09:00" "18:00"
no_  "janela que nao atravessa: 20:00 em 09-18" "20:00" "09:00" "18:00"
yes_ "inicio igual ao fim = 24 horas"           "04:00" "22:00" "22:00"
yes_ "janela vazia = 24 horas"                  "04:00" ""      ""

echo "valid_sentinel"
if valid_sentinel impl DONE;     then ok "impl DONE e valida";     else bad "impl DONE e valida" "0" "1"; fi
if valid_sentinel audit AGREED;  then ok "audit AGREED e valida";  else bad "audit AGREED e valida" "0" "1"; fi
# A que matou a rodada 1 do #157: o agente inventou a palavra, o loop parou a noite toda.
if valid_sentinel impl CHANGES_MADE; then bad "CHANGES_MADE nao e valida" "1" "0"; else ok "CHANGES_MADE nao e valida"; fi
if valid_sentinel impl AGREED;   then bad "o vocabulario do auditor nao vale para o impl" "1" "0"; else ok "o vocabulario do auditor nao vale para o impl"; fi
case "$(sentinel_vocabulary impl)"  in *"STATUS: WRONG_TICKET"*) ok "o vocabulario do impl enumera as quatro" ;; *) bad "vocabulario impl" "as quatro" "$(sentinel_vocabulary impl)" ;; esac
case "$(sentinel_vocabulary audit)" in *"VERDICT: ESCALATE"*)    ok "o vocabulario do auditor enumera as tres" ;; *) bad "vocabulario audit" "as tres" "$(sentinel_vocabulary audit)" ;; esac

echo "medidor de uso"
LEDGER=$(mktemp)
NOW=$(date +%s)
printf '%s\t%s\n' "$((NOW - 86400))"  "10.00" >> "$LEDGER"   # ontem
printf '%s\t%s\n' "$((NOW - 300))"    "5.50"  >> "$LEDGER"   # agora ha pouco
printf '%s\t%s\n' "$((NOW - 900000))" "99.00" >> "$LEDGER"   # 10 dias atras: fora da janela
eq "soma so os ultimos 7 dias"  "15.50" "$(spend_since "$((NOW - 604800))" "$LEDGER")"
eq "livro inexistente e zero"   "0.00"  "$(spend_since "$NOW" /nao/existe/ledger)"
eq "o teto e a porcentagem do orcamento" "120.00" "$(WEEKLY_BUDGET_USD=150 BUDGET_STOP_PCT=80 budget_ceiling)"
rm -f "$LEDGER"

echo "budget_period_start — o reset e um INSTANTE FIXO, nao uma janela movel"
BUDGET_PERIOD=fixed; BUDGET_RESET_DOW=friday; BUDGET_RESET_HOUR=03:00; BUDGET_TZ=America/Sao_Paulo
# O reset real desta conta: sexta 03:00 BRT.
pstart() { NOW_EPOCH=$(TZ="$BUDGET_TZ" date -d "$1" +%s) budget_period_start; }
shown()  { TZ="$BUDGET_TZ" date -d "@$(pstart "$1")" '+%Y-%m-%d %H:%M'; }
eq "numa segunda, ancora na sexta anterior"          "2026-09-11 03:00" "$(shown '2026-09-14 07:00')"
# O caso que `date -d "last friday"` erra sozinho: numa sexta ele devolve a sexta ANTERIOR,
# contando uma semana de gasto que a conta ja zerou de manha.
eq "na sexta DEPOIS do reset, ancora em hoje"        "2026-09-11 03:00" "$(shown '2026-09-11 09:00')"
eq "na sexta ANTES do reset, ancora na sexta passada" "2026-09-04 03:00" "$(shown '2026-09-11 01:00')"
eq "a virada do reset, no minuto seguinte"           "2026-09-11 03:00" "$(shown '2026-09-11 03:01')"
eq "rolling volta a ser 7 dias corridos"             "2026-09-07 07:00" \
   "$(BUDGET_PERIOD=rolling; shown '2026-09-14 07:00')"
BUDGET_PERIOD=fixed

echo "sleep_until"
# Alvo no passado retorna na hora — e por isso que suspend so ADIA o loop, nunca o trava:
# ao acordar, o relogio de parede ja passou do alvo.
BEFORE=$(date +%s); sleep_until "$(( $(date +%s) - 10 ))" "teste"; AFTER=$(date +%s)
if [ $(( AFTER - BEFORE )) -le 1 ]; then ok "alvo no passado nao dorme"; else bad "alvo no passado nao dorme" "<=1s" "$(( AFTER - BEFORE ))s"; fi

echo
echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
