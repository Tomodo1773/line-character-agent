FROM python:3.11

WORKDIR /src

EXPOSE 3100

ENV UV_PROJECT_ENVIRONMENT=.venv \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir --upgrade pip uv

COPY pyproject.toml uv.lock /src/

RUN uv sync --frozen --no-dev

COPY ./chatbot /src/chatbot

CMD ["uv", "run", "uvicorn", "chatbot.main:app", "--host", "0.0.0.0", "--port", "3100", "--reload"]
