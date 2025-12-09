FROM python:3.11

WORKDIR /home/site/wwwroot

ENV UV_PROJECT_ENVIRONMENT=.venv \
    UV_LINK_MODE=copy \
    AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true

RUN pip install --no-cache-dir --upgrade pip uv

COPY pyproject.toml uv.lock /home/site/wwwroot/

RUN uv sync --frozen --no-dev

COPY . /home/site/wwwroot

CMD ["uv", "run", "python", "-m", "azure.functions.worker"]
