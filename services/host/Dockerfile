FROM python:3.12-slim

# Installeer uv (snel pip-vervanger)
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

WORKDIR /app

# Project-manifest naar /app — verwacht context op repo-root (zie compose.yaml)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Service-code
COPY services/host /app/services/host
COPY services/mcp /app/services/mcp

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
WORKDIR /app/services/host

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
