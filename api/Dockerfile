FROM python:3.11
WORKDIR /src
EXPOSE 3100
# COPY ./requirements.txt /src/requirements.txt

# RUN pip install --no-cache-dir --upgrade -r /src/requirements.txt

RUN pip install poetry

COPY pyproject.toml* poetry.lock* /src/

RUN if [ -f pyproject.toml ]; then poetry install --no-root; fi

COPY ./ /src

CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3100", "--reload"]
