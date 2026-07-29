# Azure Container Apps は linux/amd64 のイメージのみ受け付ける。
# ARM マシンでビルドする場合は `docker build --platform linux/amd64 .` を使う。
FROM --platform=linux/amd64 python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.33 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Socket Firewall はバージョンと SHA-256 を固定する。latest から取ると
# ビルドのたびに中身が変わり、検証なしのバイナリを実行することになるため。
# 更新するときは両方を差し替える（sha256sum で取り直す）。
ARG SFW_VERSION=1.15.0
ARG SFW_SHA256=c80371910a808ea5c68916c48e5451716a91ca411cf5e422fdbd8119729b742c

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL -o /usr/local/bin/sfw \
        "https://github.com/SocketDev/sfw-free/releases/download/v${SFW_VERSION}/sfw-free-linux-x86_64" \
    && echo "${SFW_SHA256}  /usr/local/bin/sfw" | sha256sum -c - \
    && chmod +x /usr/local/bin/sfw \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN sfw uv sync --locked --no-dev --no-install-project

COPY diary_admin ./diary_admin

EXPOSE 8000

CMD ["uvicorn", "diary_admin.main:app", "--host", "0.0.0.0", "--port", "8000"]
