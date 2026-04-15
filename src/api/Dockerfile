FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY chatbot ./chatbot

CMD ["sh", "-c", "exec fastapi run --entrypoint chatbot.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]
