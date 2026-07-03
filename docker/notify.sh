#!/usr/bin/env bash
# Send a push notification via ntfy.sh. Usage: notify.sh "<title>" "<message>" ["<priority>"]
# Requires NTFY_TOPIC env var (a unique, unguessable string you also subscribe to
# in the ntfy app / web at https://ntfy.sh/<your-topic>).
set -euo pipefail

TITLE="${1:-Pycreditools Studio}"
MESSAGE="${2:-}"
PRIORITY="${3:-default}"   # min|low|default|high|urgent

if [ -z "${NTFY_TOPIC:-}" ]; then
    echo "[notify] NTFY_TOPIC not set — skipping notification: $TITLE: $MESSAGE" >&2
    exit 0
fi

curl -s \
    -H "Title: ${TITLE}" \
    -H "Priority: ${PRIORITY}" \
    -d "${MESSAGE}" \
    "https://ntfy.sh/${NTFY_TOPIC}" > /dev/null || \
    echo "[notify] failed to reach ntfy.sh (continuing)" >&2
