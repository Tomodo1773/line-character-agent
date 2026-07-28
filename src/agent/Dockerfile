# ホステッドエージェントのランタイムは linux/amd64 のみ対応する。
# ARM マシンでビルドする場合は `docker build --platform linux/amd64 .` を使う。
FROM --platform=linux/amd64 python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL -o /usr/local/bin/sfw \
        https://github.com/SocketDev/sfw-free/releases/latest/download/sfw-free-linux-x86_64 \
    && chmod +x /usr/local/bin/sfw \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN sfw uv sync --frozen --no-dev --no-install-project

COPY main.py ./
COPY character_agent ./character_agent

# プロトコルライブラリは 8088 で待ち受け、/responses と /readiness を提供する。
EXPOSE 8088

CMD ["python", "main.py"]
