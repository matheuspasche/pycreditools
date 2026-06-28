#!/usr/bin/env bash
# Run this on the HOST to watch what the ralph loop's current Claude turn is
# doing, step by step, while it's still running. The CLI only writes its final
# JSON to .ralph/logs/*.json once a turn completes — this instead tails the
# session transcript Claude Code writes incrementally inside the container.
set -euo pipefail

CONTAINER="${1:-pycreditools-ralph_loop-1}"

docker exec "$CONTAINER" sh -c '
    SESSION_FILE=$(ls -t /home/ralph/.claude/projects/-workspace/*.jsonl 2>/dev/null | head -1)
    if [ -z "$SESSION_FILE" ]; then
        echo "Nenhuma sessao encontrada ainda — o turno pode nao ter comecado."
        exit 1
    fi
    echo "Acompanhando: $SESSION_FILE (Ctrl+C para sair)"
    tail -f -n 5 "$SESSION_FILE" | while IFS= read -r line; do
        echo "$line" | jq -r "
            if .type == \"assistant\" then
                (.message.content[]? |
                    if .type == \"text\" then \"[fala] \" + (.text[0:300])
                    elif .type == \"tool_use\" then \"[ferramenta] \" + .name + \" \" + (.input | tostring | .[0:200])
                    else empty end)
            elif .type == \"user\" then
                (.message.content[]? |
                    if .type == \"tool_result\" then
                        \"[resultado] \" + ((if (.content | type) == \"array\" then .content[0].text else (.content | tostring) end)[0:200])
                    else empty end)
            else empty end" 2>/dev/null
    done
'
