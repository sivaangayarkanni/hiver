FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md requirements.txt ./
COPY src ./src
COPY data ./data
COPY artifacts ./artifacts

RUN pip install --upgrade pip && pip install .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn hiver_agent.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
