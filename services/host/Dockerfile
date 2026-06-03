FROM python:3.14-slim

# Installeer uv (snel pip-vervanger)
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

# Systeem-deps voor de CLI-transportlaag: de bash-wrappers in services/cli
# gebruiken jq (JSON-verwerking) en curl (HTTP). Zonder deze tools tonen de
# CLI-bronnen als "niet beschikbaar" in /health en falen de cli:*-modi.
# ca-certificates is nodig voor uitgaande HTTPS naar de overheidsbronnen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl jq ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Project-manifest naar /app: verwacht context op repo-root (zie compose.yaml)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Service-code: host (FastAPI), MCP-servers (stdio-subprocessen, door de host
# gestart) en CLI-wrappers (alternatief transport). Alle drie moeten in de image
# zitten zodat /health alle bronnen als "verbonden" toont.
COPY services/host /app/services/host
COPY services/mcp /app/services/mcp
COPY services/cli /app/services/cli

# Rootless: ZAD vereist een non-root image. We draaien als uid 1000 in de
# root-groep (gid 0) en geven de groep dezelfde rechten als de eigenaar
# (chmod g=u). Daardoor werkt de image ook als het platform een willekeurige
# uid toekent (OpenShift-stijl), zolang die in groep 0 zit.
RUN useradd --uid 1000 --gid 0 --create-home --home-dir /home/appuser \
        --shell /usr/sbin/nologin appuser \
    && chown -R 1000:0 /app /home/appuser \
    && chmod -R g=u /app /home/appuser
USER 1000

ENV HOME=/home/appuser
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
WORKDIR /app/services/host

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
