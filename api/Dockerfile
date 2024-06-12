FROM python:3.11
WORKDIR /src
EXPOSE 8000
COPY ./requirements.txt /src/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /src/requirements.txt

COPY ./ /src

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]