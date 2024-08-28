FROM python:3.11
WORKDIR /src
EXPOSE 3100
# COPY ./requirements.txt /src/requirements.txt

# RUN pip install --no-cache-dir --upgrade -r /src/requirements.txt

RUN pip install poetry

COPY pyproject.toml* poetry.lock* /src/

RUN if [ -f /src/pyproject.toml ]; then poetry install --no-root; fi

COPY ./chatbot /src/chatbot

CMD ["poetry", "run", "uvicorn", "chatbot.main:app", "--host", "0.0.0.0", "--port", "3100", "--reload"]
