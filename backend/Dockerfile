FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv==0.6.14

COPY pyproject.toml .
RUN uv pip install --system .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "helio.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
