FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY . /app

RUN python -m pip install --upgrade pip \
    && python -m pip install -e .

EXPOSE 3003

CMD ["python", "-m", "goofish_insight.cli", "serve-web", "--host", "0.0.0.0", "--port", "3003"]
