# Container for the "ralph loop" — runs Claude Code headless, one PRD kickoff at a
# time, against the repo mounted at /workspace. See docker/README.md for setup.
FROM node:20-slim

# Pin versions where practical for reproducible builds.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates python3 python3-pip python3-venv jq \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (official apt repo)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code@latest

WORKDIR /workspace

# Claude Code refuses --dangerously-skip-permissions when running as root (its
# own safety guard, not something we can configure around) — so this container
# runs as a dedicated non-root user instead of the image's default root.
# Auth lives in env vars (CLAUDE_CODE_OAUTH_TOKEN, GH_TOKEN), never baked into the
# image and never written under a mounted host home dir — HOME points at this
# user's own isolated home inside the container, never the real host home.
# The repo arrives as a BIND MOUNT owned by the host user, so `ralph` has to BE that
# user or every write into /workspace is denied — the loop could not create .ralph/logs,
# could not take .git/index.lock, and died on its first ticket. The base image already
# parks `node` on 1000 (the usual host uid), so that user is removed before ralph takes
# the id. Override the args if your host uid/gid is not 1000 (`id -u` / `id -g`).
ARG RALPH_UID=1000
ARG RALPH_GID=1000
RUN if getent passwd "${RALPH_UID}" >/dev/null; then userdel -r "$(getent passwd "${RALPH_UID}" | cut -d: -f1)" 2>/dev/null || true; fi \
    && if getent group "${RALPH_GID}" >/dev/null; then groupdel "$(getent group "${RALPH_GID}" | cut -d: -f1)" 2>/dev/null || true; fi \
    && groupadd --gid "${RALPH_GID}" ralph \
    && useradd --uid "${RALPH_UID}" --gid "${RALPH_GID}" --create-home --home-dir /home/ralph --shell /bin/bash ralph
ENV HOME=/home/ralph
# Pre-create .claude owned by ralph — when the docker-compose named volume
# mounts over this path, Docker copies this (now ralph-owned) directory's
# ownership into the fresh volume. Without this, a brand-new named volume
# defaults to root:root and `ralph` can't write into it (session data would
# silently fail to persist, breaking --resume across container restarts).
RUN mkdir -p /home/ralph/.claude && chown -R ralph:ralph /home/ralph

COPY ralph_loop.sh notify.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/ralph_loop.sh /usr/local/bin/notify.sh

USER ralph

ENTRYPOINT ["/usr/local/bin/ralph_loop.sh"]
