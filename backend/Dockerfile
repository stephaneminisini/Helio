FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv==0.6.14

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# The package has to be here before it is installed: hatchling reads
# pyproject.toml to decide what to ship and fails outright when the directory it
# names is missing.
COPY pyproject.toml .
COPY helio ./helio
RUN uv pip install --system .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "helio.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
