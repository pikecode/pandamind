# -- build stage --
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache-dir .

# -- runtime stage --
FROM python:3.11-slim
WORKDIR /app
RUN addgroup --system pm && adduser --system --ingroup pm pm
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY alembic/ alembic/
COPY alembic.ini ./
COPY src/ src/
RUN chown -R pm:pm /app
USER pm

ENV PYTHONPATH=src
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn pandamind.main:app --host 0.0.0.0 --port 8000"]
