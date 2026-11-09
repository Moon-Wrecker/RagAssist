FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Dependencies first (cached until pyproject.toml changes), then the project itself.
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache -r pyproject.toml
COPY src/ src/
RUN uv pip install --system --no-cache --no-deps .

# Runtime assets: model catalog, Alembic migrations and the demo seed documents.
COPY config/ config/
COPY alembic.ini .
COPY migrations/ migrations/
COPY seed/ seed/

# No credential is baked into the image: every setting is injected from the environment at run time.
EXPOSE 8000
CMD ["ragassist", "serve", "--host", "0.0.0.0", "--port", "8000"]
