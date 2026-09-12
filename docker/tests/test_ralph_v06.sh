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
CONTEXT_CAP_TOKENS=450000
if over_context_cap 449999; then bad "under the cap passes" "1" "0"; else ok "under the cap passes"; fi
if over_context_cap 450001; then ok "over the cap trips"; else bad "over the cap trips" "0" "1"; fi
if over_context_cap 0;      then bad "an unknown context (0) never trips" "1" "0"; else ok "an unknown context (0) never trips"; fi

echo "slugify"
# Accents fold to ASCII, they do not mangle: a bracket class turned "ões" into "aaes" and
# iconv//TRANSLIT under the C locale turned it into a dash.
eq "pt-BR accents fold to ASCII" "adrs-das-decisoes-congeladas"    "$(slugify 'ADRs das decisões congeladas')"
eq "a real card title"           "semente-tolerancia-e-rodadas-pareadas"    "$(slugify 'Semente, tolerância e rodadas pareadas')"
eq "no leading or trailing dashes"      "choose-grid-criterion-by" \
   "$(slugify '`choose(grid, criterion=, by=)`')"

echo
echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
