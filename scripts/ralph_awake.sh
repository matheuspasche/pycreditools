#!/usr/bin/env bash
# Mantem o HOST acordado enquanto a janela de trabalho do loop esta aberta.
#
# Por que existe: o loop roda de madrugada, e uma maquina suspensa nao roda nada. Pior,
# o `sleep` do container conta em relogio monotonico, que congela junto com a maquina —
# foi assim que uma espera de 2h37 de cota virou 8h de loop parado em 13/09. O loop ja
# nao trava mais por isso (ele dorme contra o relogio de parede), mas suspender no meio
# de um turno continua matando a chamada de API em andamento.
#
# Fora da janela ele NAO inibe nada: o PC volta a poder dormir de dia, que e quando voce
# usa. Rode num terminal e deixe aberto (ou sob tmux/systemd --user):
#
#     bash scripts/ralph_awake.sh
#
# Ctrl+C libera o inibidor na hora.
set -uo pipefail

START="${WORK_WINDOW_START:-22:00}"
END="${WORK_WINDOW_END:-08:00}"
TZ_NAME="${WORK_WINDOW_TZ:-America/Sao_Paulo}"

command -v systemd-inhibit >/dev/null || { echo "systemd-inhibit nao encontrado — sem isso, configure a suspensao automatica para 'nunca' nas preferencias de energia."; exit 1; }

in_window() {
    local now start end
    now=$((10#$(TZ="$TZ_NAME" date +%H%M))); start=$((10#${START//:/})); end=$((10#${END//:/}))
    if [ "$start" -lt "$end" ]; then [ "$now" -ge "$start" ] && [ "$now" -lt "$end" ]
    else [ "$now" -ge "$start" ] || [ "$now" -lt "$end" ]; fi
}

echo "[ralph_awake] janela ${START}-${END} (${TZ_NAME}). Fora dela, o PC dorme normalmente."
INHIBITOR_PID=""
cleanup() { [ -n "$INHIBITOR_PID" ] && kill "$INHIBITOR_PID" 2>/dev/null; echo; echo "[ralph_awake] inibidor liberado."; exit 0; }
trap cleanup INT TERM

while true; do
    if in_window; then
        if [ -z "$INHIBITOR_PID" ] || ! kill -0 "$INHIBITOR_PID" 2>/dev/null; then
            systemd-inhibit --what=sleep:idle --who="ralph loop v0.6" \
                --why="implementacao noturna do mapa da v0.6" --mode=block \
                sleep infinity &
            INHIBITOR_PID=$!
            echo "[ralph_awake] $(date +%H:%M) janela aberta — suspensao inibida (pid $INHIBITOR_PID)"
        fi
    elif [ -n "$INHIBITOR_PID" ]; then
        kill "$INHIBITOR_PID" 2>/dev/null; INHIBITOR_PID=""
        echo "[ralph_awake] $(date +%H:%M) janela fechada — o PC pode dormir de novo"
    fi
    sleep 60
done
