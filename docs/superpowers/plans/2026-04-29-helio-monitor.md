# Helio Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted solar analytics platform that ingests Enphase API data, stores it in PostgreSQL, and serves a React dashboard with historical comparisons, efficiency tracking, and degradation alerts.

**Architecture:** Python/FastAPI backend with SQLAlchemy 2 async ORM, APScheduler for daily polling, and a React/Vite frontend. All services run in Docker Compose. The backend exposes a REST API; the frontend fetches from it at runtime using `VITE_API_BASE_URL`.

**Tech Stack:** Python 3.13, FastAPI 0.110+, SQLAlchemy 2.x async, Alembic 1.13+, httpx 0.27+, APScheduler 3.x, pvlib, PostgreSQL 15, React 18, Vite, Tailwind CSS, Docker Compose.

---

## Phase 0 — Project Scaffold

### Task 1: Backend pyproject.toml and directory skeleton

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/helio/__init__.py`
- Create: `backend/helio/core/__init__.py`
- Create: `backend/helio/db/__init__.py`
- Create: `backend/helio/ingestion/__init__.py`
- Create: `backend/helio/analytics/__init__.py`
- Create: `backend/helio/api/__init__.py`
- Create: `backend/helio/api/routes/__init__.py`
- Create: `backend/helio/api/schemas/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/unit/__init__.py`
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/fixtures/__init__.py`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/.gitkeep`
- Create: `backend/alembic.ini`

- [ ] **Step 1: Create the backend directory tree**

```bash
cd /path/to/repo
mkdir -p backend/helio/core
mkdir -p backend/helio/db
mkdir -p backend/helio/ingestion
mkdir -p backend/helio/analytics
mkdir -p backend/helio/api/routes
mkdir -p backend/helio/api/schemas
mkdir -p backend/tests/unit
mkdir -p backend/tests/integration
mkdir -p backend/tests/fixtures
mkdir -p backend/alembic/versions
touch backend/helio/__init__.py
touch backend/helio/core/__init__.py
touch backend/helio/db/__init__.py
touch backend/helio/ingestion/__init__.py
touch backend/helio/analytics/__init__.py
touch backend/helio/api/__init__.py
touch backend/helio/api/routes/__init__.py
touch backend/helio/api/schemas/__init__.py
touch backend/tests/__init__.py
touch backend/tests/unit/__init__.py
touch backend/tests/integration/__init__.py
touch backend/tests/fixtures/__init__.py
touch backend/alembic/versions/.gitkeep
```

- [ ] **Step 2: Write `backend/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "helio"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "alembic>=1.13.0",
    "asyncpg>=0.29.0",
    "httpx>=0.27.0",
    "apscheduler>=3.10.0",
    "pydantic-settings>=2.0.0",
    "pvlib>=0.10.0",
    "cryptography>=42.0.0",
    "loguru>=0.7.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "ruff>=0.4.0",
    "respx>=0.21.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 88
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
```

- [ ] **Step 3: Write `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = postgresql+asyncpg://helio:changeme@localhost:5432/helio

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 4: Write `backend/alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import Base after models are defined (Phase 1 will populate this)
target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "chore(scaffold): create backend directory skeleton and pyproject.toml"
```

---

### Task 2: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]"

COPY . .

CMD ["uvicorn", "helio.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Commit**

```bash
git add backend/Dockerfile
git commit -m "chore(scaffold): add backend Dockerfile"
```

---

### Task 3: Frontend Vite scaffold and Dockerfile

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tsconfig.json`
- Create: `frontend/Dockerfile`

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "helio-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "recharts": "^2.12.0",
    "clsx": "^2.1.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0"
  }
}
```

- [ ] **Step 2: Write `frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_API_BASE_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **Step 3: Write `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Write `frontend/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        solar: {
          50: "#fffbeb",
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
        },
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 5: Write `frontend/postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 6: Write `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Helio Monitor</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Write `frontend/src/main.tsx`**

```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 8: Write `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 9: Write `frontend/src/App.tsx`** (placeholder — replaced in Phase 7)

```typescript
export default function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
      <p className="text-solar-400 text-lg">Helio Monitor — loading...</p>
    </div>
  );
}
```

- [ ] **Step 10: Write `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json .
RUN npm install

COPY . .
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 11: Write `frontend/nginx.conf`**

```nginx
server {
    listen 80;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

- [ ] **Step 12: Commit**

```bash
git add frontend/
git commit -m "chore(scaffold): add frontend Vite/React/Tailwind scaffold and Dockerfile"
```

---

## Phase 1 — Database Schema & Migrations

### Task 4: Config and crypto modules

**Files:**
- Create: `backend/helio/core/config.py`
- Create: `backend/helio/core/crypto.py`
- Create: `backend/tests/unit/test_crypto.py`

- [ ] **Step 1: Write the failing test for crypto**

`backend/tests/unit/test_crypto.py`:

```python
import pytest
from helio.core.crypto import encrypt, decrypt


def test_encrypt_decrypt_roundtrip():
    key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    plaintext = "my-secret-token"
    ciphertext = encrypt(plaintext, key)
    assert ciphertext != plaintext
    assert decrypt(ciphertext, key) == plaintext


def test_encrypt_produces_different_ciphertexts():
    key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    plaintext = "my-secret-token"
    assert encrypt(plaintext, key) != encrypt(plaintext, key)


def test_decrypt_wrong_key_raises():
    key1 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    key2 = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
    ciphertext = encrypt("secret", key1)
    with pytest.raises(Exception):
        decrypt(ciphertext, key2)
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend
uv run pytest tests/unit/test_crypto.py -v
```

Expected: `ImportError` or `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/helio/core/crypto.py`**

```python
from cryptography.fernet import Fernet


def encrypt(plaintext: str, key: str) -> str:
    """Encrypt a plaintext string using Fernet symmetric encryption.

    Args:
        plaintext: The string to encrypt.
        key: A URL-safe base64-encoded 32-byte Fernet key.

    Returns:
        The encrypted token as a UTF-8 string.
    """
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str) -> str:
    """Decrypt a Fernet-encrypted token back to plaintext.

    Args:
        ciphertext: The encrypted token string.
        key: The same Fernet key used to encrypt.

    Returns:
        The original plaintext string.

    Raises:
        cryptography.fernet.InvalidToken: If key is wrong or token is corrupted.
    """
    f = Fernet(key.encode())
    return f.decrypt(ciphertext.encode()).decode()
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
uv run pytest tests/unit/test_crypto.py -v
```

Expected: 3 passed

- [ ] **Step 5: Write `backend/helio/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://helio:changeme@db:5432/helio"
    enphase_client_id: str = ""
    enphase_client_secret: str = ""
    enphase_system_id: str = ""
    fernet_key: str = ""
    nrel_api_key: str = ""
    irradiance_source: str = "nrel"
    poll_hour: int = 4
    poll_minute: int = 0
    tz: str = "America/Montreal"
    vite_api_base_url: str = "http://localhost:8000"


settings = Settings()
```

- [ ] **Step 6: Commit**

```bash
git add backend/helio/core/ backend/tests/unit/test_crypto.py
git commit -m "feat(core): add config settings and Fernet crypto module"
```

---

### Task 5: SQLAlchemy models

**Files:**
- Create: `backend/helio/db/models.py`
- Create: `backend/helio/db/session.py`
- Create: `backend/tests/unit/test_models.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_models.py`:

```python
from helio.db.models import (
    System,
    EnergyInterval,
    DailySummary,
    MonthlySummary,
    Irradiance,
    PollLog,
)


def test_system_tablename():
    assert System.__tablename__ == "systems"


def test_energy_interval_tablename():
    assert EnergyInterval.__tablename__ == "energy_intervals"


def test_daily_summary_tablename():
    assert DailySummary.__tablename__ == "daily_summaries"


def test_monthly_summary_tablename():
    assert MonthlySummary.__tablename__ == "monthly_summaries"


def test_irradiance_tablename():
    assert Irradiance.__tablename__ == "irradiance"


def test_poll_log_tablename():
    assert PollLog.__tablename__ == "poll_log"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/unit/test_models.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `backend/helio/db/models.py`**

```python
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class System(Base):
    __tablename__ = "systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enphase_system_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(256))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    system_size_kw: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    panel_count: Mapped[int | None] = mapped_column(Integer)
    panel_wattage_w: Mapped[int | None] = mapped_column(Integer)
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    install_date: Mapped[date] = mapped_column(Date, nullable=False)
    tilt_angle_deg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    azimuth_deg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    degradation_rate: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0.5"))
    irradiance_source: Mapped[str] = mapped_column(String(32), default="nrel")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    intervals: Mapped[list["EnergyInterval"]] = relationship(back_populates="system")
    daily_summaries: Mapped[list["DailySummary"]] = relationship(back_populates="system")
    monthly_summaries: Mapped[list["MonthlySummary"]] = relationship(back_populates="system")
    irradiance_records: Mapped[list["Irradiance"]] = relationship(back_populates="system")
    poll_logs: Mapped[list["PollLog"]] = relationship(back_populates="system")


class EnergyInterval(Base):
    __tablename__ = "energy_intervals"
    __table_args__ = (UniqueConstraint("system_id", "interval_start"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id"), nullable=False)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    production_wh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    consumption_wh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    net_wh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    system: Mapped["System"] = relationship(back_populates="intervals")


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (UniqueConstraint("system_id", "day"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    production_kwh: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    consumption_kwh: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    peak_power_w: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    peak_power_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_count: Mapped[int | None] = mapped_column(Integer)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    system: Mapped["System"] = relationship(back_populates="daily_summaries")


class MonthlySummary(Base):
    __tablename__ = "monthly_summaries"
    __table_args__ = (UniqueConstraint("system_id", "month"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id"), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    production_kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    theoretical_kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    performance_ratio: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    expected_pr: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    system: Mapped["System"] = relationship(back_populates="monthly_summaries")


class Irradiance(Base):
    __tablename__ = "irradiance"
    __table_args__ = (UniqueConstraint("system_id", "day", "source"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    ghi_kwh_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    dni_kwh_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    poa_kwh_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    source: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    system: Mapped["System"] = relationship(back_populates="irradiance_records")


class PollLog(Base):
    __tablename__ = "poll_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int | None] = mapped_column(ForeignKey("systems.id"))
    poll_type: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(16))
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    date_range_start: Mapped[date | None] = mapped_column(Date)
    date_range_end: Mapped[date | None] = mapped_column(Date)

    system: Mapped["System | None"] = relationship(back_populates="poll_logs")
```

- [ ] **Step 4: Write `backend/helio/db/session.py`**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helio.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
cd backend
uv run pytest tests/unit/test_models.py -v
```

Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add backend/helio/db/ backend/tests/unit/test_models.py
git commit -m "feat(db): add SQLAlchemy models and async session factory"
```

---

### Task 6: Alembic initial migration

**Files:**
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_initial_schema.py`

**Note:** This task requires a running Postgres instance. Run `docker compose up db -d` before running migrations.

- [ ] **Step 1: Update `backend/alembic/env.py` to import models**

Replace the `target_metadata = None` line:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from helio.db.models import Base  # noqa: F401 — registers all models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 2: Generate the migration**

```bash
cd backend
docker compose up db -d   # from repo root first if not running
uv run alembic revision --autogenerate -m "initial_schema"
```

Expected: a file appears in `alembic/versions/` with a hash prefix like `abc123_initial_schema.py`

- [ ] **Step 3: Rename it to `001_initial_schema.py` and verify its `upgrade()` function**

Rename the generated file to `001_initial_schema.py`. Confirm its `upgrade()` creates tables: `systems`, `energy_intervals`, `daily_summaries`, `monthly_summaries`, `irradiance`, `poll_log`. If any are missing, check that models.py imports are all present in env.py.

- [ ] **Step 4: Run the migration**

```bash
cd backend
uv run alembic upgrade head
```

Expected:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001..., initial_schema
```

- [ ] **Step 5: Verify tables exist**

```bash
docker compose exec db psql -U helio -d helio -c "\dt"
```

Expected: 6 tables listed: `systems`, `energy_intervals`, `daily_summaries`, `monthly_summaries`, `irradiance`, `poll_log`

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/
git commit -m "feat(db): add initial Alembic migration with all tables"
```

---

## Phase 2 — Enphase API Client

### Task 7: Enphase client with OAuth and interval fetching

**Files:**
- Create: `backend/helio/ingestion/enphase_client.py`
- Create: `backend/tests/unit/test_enphase_client.py`
- Create: `backend/tests/fixtures/enphase_intervals.json`
- Create: `backend/tests/fixtures/enphase_system.json`

- [ ] **Step 1: Write fixture files**

`backend/tests/fixtures/enphase_intervals.json`:
```json
{
  "system_id": 12345,
  "intervals": [
    {"end_at": 1714262400, "wh_del": 1250},
    {"end_at": 1714263300, "wh_del": 1480},
    {"end_at": 1714264200, "wh_del": 1390}
  ]
}
```

`backend/tests/fixtures/enphase_system.json`:
```json
{
  "system_id": 12345,
  "name": "My Solar System",
  "public_name": "My Solar System",
  "timezone": "America/Montreal",
  "address": {
    "state": "QC",
    "country": "CA",
    "zip": "H1A 0A1"
  },
  "connection_type": "eth",
  "status": "normal",
  "last_report_at": 1714262400,
  "last_energy_at": 1714262400,
  "operational_at": 1672531200,
  "attachment_type": "microinverter",
  "reference": "HELIO-001"
}
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/unit/test_enphase_client.py`:

```python
import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from helio.ingestion.enphase_client import EnphaseClient, IntervalData

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def client():
    return EnphaseClient(
        client_id="test-id",
        client_secret="test-secret",
        system_id="12345",
        access_token="test-token",
        refresh_token="test-refresh",
        fernet_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )


@pytest.fixture
def intervals_payload():
    return json.loads((FIXTURES / "enphase_intervals.json").read_text())


@respx.mock
@pytest.mark.asyncio
async def test_get_intervals_returns_interval_data(client, intervals_payload):
    respx.get(
        "https://api.enphaseenergy.com/api/v4/systems/12345/telemetry/production_micro"
    ).mock(return_value=httpx.Response(200, json=intervals_payload))

    result = await client.get_intervals(date(2024, 4, 28), date(2024, 4, 28))

    assert len(result) == 3
    assert isinstance(result[0], IntervalData)
    assert result[0].production_wh == 1250


@respx.mock
@pytest.mark.asyncio
async def test_get_intervals_retries_on_429(client):
    respx.get(
        "https://api.enphaseenergy.com/api/v4/systems/12345/telemetry/production_micro"
    ).mock(
        side_effect=[
            httpx.Response(429, json={"message": "rate limit"}),
            httpx.Response(200, json={"system_id": 12345, "intervals": []}),
        ]
    )

    result = await client.get_intervals(date(2024, 4, 28), date(2024, 4, 28))
    assert result == []


@respx.mock
@pytest.mark.asyncio
async def test_get_intervals_raises_after_max_retries(client):
    respx.get(
        "https://api.enphaseenergy.com/api/v4/systems/12345/telemetry/production_micro"
    ).mock(return_value=httpx.Response(429, json={"message": "rate limit"}))

    with pytest.raises(Exception, match="rate limit"):
        await client.get_intervals(date(2024, 4, 28), date(2024, 4, 28))
```

- [ ] **Step 3: Run to confirm failure**

```bash
cd backend
uv run pytest tests/unit/test_enphase_client.py -v
```

Expected: `ImportError`

- [ ] **Step 4: Write `backend/helio/ingestion/enphase_client.py`**

```python
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
from loguru import logger

BASE_URL = "https://api.enphaseenergy.com/api/v4"
TOKEN_URL = "https://api.enphaseenergy.com/oauth/token"
MAX_RETRIES = 3


@dataclass
class IntervalData:
    """A single 15-minute production interval."""

    interval_start: datetime
    duration_seconds: int
    production_wh: float


class EnphaseClient:
    """Async client for Enphase API v4 with token management and retry logic.

    Args:
        client_id: Enphase OAuth application client ID.
        client_secret: Enphase OAuth application client secret.
        system_id: Enphase system ID to query.
        access_token: Current OAuth access token (may be empty on first run).
        refresh_token: OAuth refresh token for renewing access.
        fernet_key: Fernet key used to encrypt tokens before DB storage.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        system_id: str,
        access_token: str,
        refresh_token: str,
        fernet_key: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._system_id = system_id
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._fernet_key = fernet_key

    async def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
    ) -> dict:
        """Execute an authenticated request with exponential backoff on 429/503.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full URL to request.
            params: Optional query parameters.

        Returns:
            Parsed JSON response body.

        Raises:
            httpx.HTTPStatusError: After MAX_RETRIES failed attempts.
        """
        headers = {"Authorization": f"Bearer {self._access_token}"}
        for attempt in range(MAX_RETRIES):
            async with httpx.AsyncClient() as http:
                response = await http.request(method, url, params=params, headers=headers)
            if response.status_code == 429:
                wait = 2**attempt
                logger.warning("Rate limited by Enphase API, retrying in {}s", wait)
                if attempt == MAX_RETRIES - 1:
                    response.raise_for_status()
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        response.raise_for_status()  # unreachable but satisfies type checker
        return {}

    async def get_intervals(self, start: date, end: date) -> list[IntervalData]:
        """Fetch 15-minute production intervals for a date range.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            List of IntervalData ordered by interval_start ascending.

        Raises:
            httpx.HTTPStatusError: On non-retryable API errors.
        """
        url = f"{BASE_URL}/systems/{self._system_id}/telemetry/production_micro"
        params = {
            "start_at": int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()),
            "end_at": int(datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc).timestamp()),
        }
        data = await self._request("GET", url, params=params)
        result = []
        for item in data.get("intervals", []):
            end_at = datetime.fromtimestamp(item["end_at"], tz=timezone.utc)
            interval_start = datetime.fromtimestamp(
                item["end_at"] - 900, tz=timezone.utc
            )
            result.append(
                IntervalData(
                    interval_start=interval_start,
                    duration_seconds=900,
                    production_wh=float(item.get("wh_del", 0)),
                )
            )
        return result

    async def get_system_info(self) -> dict:
        """Fetch system metadata from the Enphase API.

        Returns:
            Raw system metadata dict.

        Raises:
            httpx.HTTPStatusError: On API errors.
        """
        url = f"{BASE_URL}/systems/{self._system_id}"
        return await self._request("GET", url)

    async def refresh_access_token(self) -> str:
        """Refresh the OAuth access token using the stored refresh token.

        Returns:
            The new access token string.

        Raises:
            httpx.HTTPStatusError: On token refresh failure.
        """
        async with httpx.AsyncClient() as http:
            response = await http.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                auth=(self._client_id, self._client_secret),
            )
        response.raise_for_status()
        body = response.json()
        self._access_token = body["access_token"]
        self._refresh_token = body.get("refresh_token", self._refresh_token)
        logger.info("Enphase access token refreshed successfully")
        return self._access_token
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
uv run pytest tests/unit/test_enphase_client.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/helio/ingestion/enphase_client.py backend/tests/
git commit -m "feat(ingestion): add EnphaseClient with OAuth, intervals, and retry logic"
```

---

## Phase 3 — Irradiance Client

### Task 8: Irradiance client with POA calculation

**Files:**
- Create: `backend/helio/ingestion/irradiance_client.py`
- Create: `backend/tests/unit/test_irradiance_client.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/unit/test_irradiance_client.py`:

```python
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from helio.ingestion.irradiance_client import NRELClient, NASAClient, compute_poa


def test_compute_poa_returns_positive_value():
    poa = compute_poa(
        ghi=5.0,
        dni=4.0,
        tilt=30.0,
        azimuth=180.0,
        latitude=45.0,
        target_date=date(2024, 6, 21),
    )
    assert poa > 0


def test_compute_poa_zero_ghi_returns_zero():
    poa = compute_poa(
        ghi=0.0,
        dni=0.0,
        tilt=30.0,
        azimuth=180.0,
        latitude=45.0,
        target_date=date(2024, 6, 21),
    )
    assert poa == 0.0


@respx.mock
@pytest.mark.asyncio
async def test_nrel_client_returns_irradiance():
    respx.get("https://developer.nrel.gov/api/solar/solar_resource/v1.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "outputs": {
                    "avg_ghi": {"annual": 4.5},
                    "avg_dni": {"annual": 4.0},
                }
            },
        )
    )
    client = NRELClient(api_key="test-key")
    result = await client.get_daily_irradiance(
        latitude=45.5,
        longitude=-73.6,
        target_date=date(2024, 4, 28),
    )
    assert result["ghi"] > 0
    assert result["dni"] > 0


@respx.mock
@pytest.mark.asyncio
async def test_nasa_client_returns_irradiance():
    respx.get("https://power.larc.nasa.gov/api/temporal/daily/point").mock(
        return_value=httpx.Response(
            200,
            json={
                "properties": {
                    "parameter": {
                        "ALLSKY_SFC_SW_DWN": {"20240428": 5.1},
                        "ALLSKY_SFC_SW_DNI": {"20240428": 4.2},
                    }
                }
            },
        )
    )
    client = NASAClient()
    result = await client.get_daily_irradiance(
        latitude=45.5,
        longitude=-73.6,
        target_date=date(2024, 4, 28),
    )
    assert result["ghi"] == pytest.approx(5.1)
    assert result["dni"] == pytest.approx(4.2)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/unit/test_irradiance_client.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `backend/helio/ingestion/irradiance_client.py`**

```python
from abc import ABC, abstractmethod
from datetime import date

import httpx
import pvlib
import pandas as pd
from loguru import logger

NREL_URL = "https://developer.nrel.gov/api/solar/solar_resource/v1.json"
NASA_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def compute_poa(
    ghi: float,
    dni: float,
    tilt: float,
    azimuth: float,
    latitude: float,
    target_date: date,
) -> float:
    """Compute Plane-of-Array irradiance using pvlib Perez transposition model.

    Args:
        ghi: Global Horizontal Irradiance in kWh/m2/day.
        dni: Direct Normal Irradiance in kWh/m2/day.
        tilt: Panel tilt angle in degrees from horizontal.
        azimuth: Panel azimuth in degrees (180 = south-facing).
        latitude: Site latitude in decimal degrees.
        target_date: The date for solar position calculation.

    Returns:
        Plane-of-Array irradiance in kWh/m2/day.
    """
    if ghi == 0.0 and dni == 0.0:
        return 0.0

    times = pd.date_range(
        start=f"{target_date} 12:00:00", periods=1, freq="h", tz="UTC"
    )
    location = pvlib.location.Location(latitude=latitude, longitude=0)
    solar_position = location.get_solarposition(times)

    dhi = max(0.0, ghi - dni * float(solar_position["zenith"].cos().iloc[0]))

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        solar_zenith=solar_position["apparent_zenith"].iloc[0],
        solar_azimuth=solar_position["azimuth"].iloc[0],
        dni=dni * 1000,
        ghi=ghi * 1000,
        dhi=max(0.0, dhi * 1000),
        model="haydavies",
    )
    return round(float(poa["poa_global"]) / 1000, 4)


class IrradianceClient(ABC):
    """Abstract base for irradiance data providers."""

    @abstractmethod
    async def get_daily_irradiance(
        self, latitude: float, longitude: float, target_date: date
    ) -> dict[str, float]:
        """Fetch daily GHI and DNI for a location and date.

        Args:
            latitude: Site latitude in decimal degrees.
            longitude: Site longitude in decimal degrees.
            target_date: Date to fetch irradiance for.

        Returns:
            Dict with keys 'ghi' and 'dni' in kWh/m2/day.

        Raises:
            httpx.HTTPStatusError: On API errors.
        """


class NRELClient(IrradianceClient):
    """NREL Solar Resource Data API client.

    Args:
        api_key: NREL developer API key.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def get_daily_irradiance(
        self, latitude: float, longitude: float, target_date: date
    ) -> dict[str, float]:
        params = {
            "api_key": self._api_key,
            "lat": latitude,
            "lon": longitude,
        }
        async with httpx.AsyncClient() as http:
            response = await http.get(NREL_URL, params=params)
        response.raise_for_status()
        outputs = response.json().get("outputs", {})
        ghi = float(outputs.get("avg_ghi", {}).get("annual", 0))
        dni = float(outputs.get("avg_dni", {}).get("annual", 0))
        logger.debug("NREL irradiance for {}: ghi={}, dni={}", target_date, ghi, dni)
        return {"ghi": ghi, "dni": dni}


class NASAClient(IrradianceClient):
    """NASA POWER daily irradiance API client (no API key required)."""

    async def get_daily_irradiance(
        self, latitude: float, longitude: float, target_date: date
    ) -> dict[str, float]:
        date_str = target_date.strftime("%Y%m%d")
        params = {
            "parameters": "ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DNI",
            "community": "RE",
            "longitude": longitude,
            "latitude": latitude,
            "start": date_str,
            "end": date_str,
            "format": "JSON",
        }
        async with httpx.AsyncClient() as http:
            response = await http.get(NASA_URL, params=params)
        response.raise_for_status()
        props = response.json().get("properties", {}).get("parameter", {})
        ghi = float(props.get("ALLSKY_SFC_SW_DWN", {}).get(date_str, 0))
        dni = float(props.get("ALLSKY_SFC_SW_DNI", {}).get(date_str, 0))
        logger.debug("NASA irradiance for {}: ghi={}, dni={}", target_date, ghi, dni)
        return {"ghi": ghi, "dni": dni}
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
uv run pytest tests/unit/test_irradiance_client.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/helio/ingestion/irradiance_client.py backend/tests/unit/test_irradiance_client.py
git commit -m "feat(ingestion): add irradiance client (NREL + NASA) with POA calculation"
```

---

## Phase 4 — Poller & Scheduler

### Task 9: Poller with gap detection and backfill

**Files:**
- Create: `backend/helio/ingestion/poller.py`
- Create: `backend/tests/unit/test_poller.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/unit/test_poller.py`:

```python
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helio.ingestion.poller import detect_gaps


@pytest.mark.asyncio
async def test_detect_gaps_returns_missing_dates():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(return_value=[date(2024, 4, 1), date(2024, 4, 3)])
                )
            )
        )
    )

    gaps = await detect_gaps(
        session=mock_session,
        system_id=1,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 4, 4),
    )
    assert date(2024, 4, 2) in gaps
    assert date(2024, 4, 4) in gaps
    assert date(2024, 4, 1) not in gaps
    assert date(2024, 4, 3) not in gaps


@pytest.mark.asyncio
async def test_detect_gaps_no_gaps():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(
                        return_value=[date(2024, 4, 1), date(2024, 4, 2), date(2024, 4, 3)]
                    )
                )
            )
        )
    )

    gaps = await detect_gaps(
        session=mock_session,
        system_id=1,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 4, 3),
    )
    assert gaps == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/unit/test_poller.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `backend/helio/ingestion/poller.py`**

```python
from datetime import date, datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import DailySummary, EnergyInterval, Irradiance, PollLog
from helio.ingestion.enphase_client import EnphaseClient, IntervalData
from helio.ingestion.irradiance_client import IrradianceClient


async def detect_gaps(
    session: AsyncSession,
    system_id: int,
    start_date: date,
    end_date: date,
) -> list[date]:
    """Return dates in [start_date, end_date] that have no daily_summary row.

    Args:
        session: Active async database session.
        system_id: System to check gaps for.
        start_date: First date to check (inclusive).
        end_date: Last date to check (inclusive).

    Returns:
        Sorted list of dates with missing data.
    """
    stmt = select(DailySummary.day).where(
        DailySummary.system_id == system_id,
        DailySummary.day >= start_date,
        DailySummary.day <= end_date,
    )
    result = await session.execute(stmt)
    present = set(result.scalars().all())
    all_dates = {
        start_date + timedelta(days=i)
        for i in range((end_date - start_date).days + 1)
    }
    return sorted(all_dates - present)


async def poll_intervals(
    session: AsyncSession,
    client: EnphaseClient,
    system_id: int,
    start_date: date,
    end_date: date,
) -> tuple[int, int]:
    """Fetch intervals from Enphase and upsert them into energy_intervals.

    Args:
        session: Active async database session.
        client: Authenticated EnphaseClient instance.
        system_id: DB system ID for the target system.
        start_date: Start of date range.
        end_date: End of date range.

    Returns:
        Tuple of (records_fetched, records_inserted).
    """
    started_at = datetime.now(tz=timezone.utc)
    poll_log = PollLog(
        system_id=system_id,
        poll_type="intervals",
        started_at=started_at,
        status="running",
    )
    session.add(poll_log)
    await session.flush()

    try:
        intervals = await client.get_intervals(start_date, end_date)
        records_fetched = len(intervals)
        records_inserted = 0

        for iv in intervals:
            existing = await session.execute(
                select(EnergyInterval).where(
                    EnergyInterval.system_id == system_id,
                    EnergyInterval.interval_start == iv.interval_start,
                )
            )
            if existing.scalar_one_or_none() is None:
                session.add(
                    EnergyInterval(
                        system_id=system_id,
                        interval_start=iv.interval_start,
                        duration_seconds=iv.duration_seconds,
                        production_wh=iv.production_wh,
                    )
                )
                records_inserted += 1

        poll_log.status = "success"
        poll_log.completed_at = datetime.now(tz=timezone.utc)
        poll_log.records_fetched = records_fetched
        poll_log.records_inserted = records_inserted
        poll_log.date_range_start = start_date
        poll_log.date_range_end = end_date
        await session.commit()
        logger.info(
            "Polled intervals {}-{}: fetched={}, inserted={}",
            start_date, end_date, records_fetched, records_inserted,
        )
        return records_fetched, records_inserted

    except Exception as exc:
        poll_log.status = "error"
        poll_log.error_message = str(exc)
        poll_log.completed_at = datetime.now(tz=timezone.utc)
        await session.commit()
        logger.error("Poll failed for {}-{}: {}", start_date, end_date, exc)
        raise


async def poll_irradiance(
    session: AsyncSession,
    client: IrradianceClient,
    system_id: int,
    latitude: float,
    longitude: float,
    tilt: float,
    azimuth: float,
    target_date: date,
    source: str,
) -> None:
    """Fetch irradiance for one day and upsert into irradiance table.

    Args:
        session: Active async database session.
        client: IrradianceClient (NRELClient or NASAClient).
        system_id: DB system ID.
        latitude: Site latitude.
        longitude: Site longitude.
        tilt: Panel tilt in degrees.
        azimuth: Panel azimuth in degrees.
        target_date: Date to fetch.
        source: 'nrel' or 'nasa'.
    """
    from helio.ingestion.irradiance_client import compute_poa

    data = await client.get_daily_irradiance(latitude, longitude, target_date)
    poa = compute_poa(
        ghi=data["ghi"],
        dni=data["dni"],
        tilt=tilt,
        azimuth=azimuth,
        latitude=latitude,
        target_date=target_date,
    )
    existing = await session.execute(
        select(Irradiance).where(
            Irradiance.system_id == system_id,
            Irradiance.day == target_date,
            Irradiance.source == source,
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        session.add(
            Irradiance(
                system_id=system_id,
                day=target_date,
                ghi_kwh_m2=data["ghi"],
                dni_kwh_m2=data["dni"],
                poa_kwh_m2=poa,
                source=source,
            )
        )
    else:
        row.ghi_kwh_m2 = data["ghi"]
        row.dni_kwh_m2 = data["dni"]
        row.poa_kwh_m2 = poa

    await session.commit()
    logger.debug("Irradiance stored for {} (source={})", target_date, source)
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
uv run pytest tests/unit/test_poller.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/helio/ingestion/poller.py backend/tests/unit/test_poller.py
git commit -m "feat(ingestion): add poller with gap detection, interval upsert, and irradiance storage"
```

---

## Phase 5 — Analytics Engine

### Task 10: Daily and monthly summarizer

**Files:**
- Create: `backend/helio/analytics/summarizer.py`
- Create: `backend/tests/unit/test_summarizer.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/unit/test_summarizer.py`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helio.analytics.summarizer import build_daily_summary, build_monthly_summary


@pytest.mark.asyncio
async def test_build_daily_summary_aggregates_correctly():
    mock_session = AsyncMock()
    mock_intervals = [
        MagicMock(production_wh=Decimal("500"), interval_start=datetime(2024, 4, 28, 10, 0, tzinfo=timezone.utc)),
        MagicMock(production_wh=Decimal("800"), interval_start=datetime(2024, 4, 28, 12, 0, tzinfo=timezone.utc)),
        MagicMock(production_wh=Decimal("400"), interval_start=datetime(2024, 4, 28, 14, 0, tzinfo=timezone.utc)),
    ]
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=mock_intervals))
            )
        )
    )
    mock_session.merge = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    await build_daily_summary(mock_session, system_id=1, day=date(2024, 4, 28))

    mock_session.merge.assert_called_once()
    call_arg = mock_session.merge.call_args[0][0]
    assert call_arg.production_kwh == pytest.approx(Decimal("1.700"), rel=1e-3)
    assert call_arg.peak_power_w is not None


@pytest.mark.asyncio
async def test_build_monthly_summary_calculates_pr():
    mock_session = AsyncMock()

    daily_rows = [
        MagicMock(production_kwh=Decimal("30")),
        MagicMock(production_kwh=Decimal("35")),
    ]
    irradiance_rows = [
        MagicMock(poa_kwh_m2=Decimal("5.0")),
        MagicMock(poa_kwh_m2=Decimal("6.0")),
    ]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=daily_rows))
                )
            )
        return MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=irradiance_rows))
            )
        )

    mock_session.execute = mock_execute
    mock_session.merge = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    # system_size_kw=10, install_date needs to be before month
    from datetime import date as d
    mock_system = MagicMock(system_size_kw=Decimal("10"), install_date=d(2023, 1, 1), degradation_rate=Decimal("0.5"))

    await build_monthly_summary(
        mock_session,
        system_id=1,
        month=date(2024, 4, 1),
        system=mock_system,
    )

    mock_session.merge.assert_called_once()
    call_arg = mock_session.merge.call_args[0][0]
    assert call_arg.production_kwh == pytest.approx(Decimal("65"), rel=1e-3)
    assert call_arg.performance_ratio is not None
    assert 0 < float(call_arg.performance_ratio) < 2
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/unit/test_summarizer.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `backend/helio/analytics/summarizer.py`**

```python
from datetime import date
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import DailySummary, EnergyInterval, Irradiance, MonthlySummary, System


async def build_daily_summary(
    session: AsyncSession,
    system_id: int,
    day: date,
) -> DailySummary:
    """Aggregate energy_intervals for one day into a daily_summary row.

    Args:
        session: Active async database session.
        system_id: System to summarize.
        day: Date to summarize.

    Returns:
        The upserted DailySummary instance.
    """
    stmt = select(EnergyInterval).where(
        EnergyInterval.system_id == system_id,
        EnergyInterval.interval_start >= day,
        EnergyInterval.interval_start < date(day.year, day.month, day.day + 1)
        if day.day < 28
        else date(day.year + (1 if day.month == 12 else 0), (day.month % 12) + 1 if day.day >= 28 else day.month, 1),
    )
    result = await session.execute(stmt)
    intervals = result.scalars().all()

    if not intervals:
        logger.warning("No intervals found for system={} day={}", system_id, day)

    total_wh = sum(float(iv.production_wh or 0) for iv in intervals)
    peak = max((float(iv.production_wh or 0) for iv in intervals), default=0.0)
    peak_at = next(
        (iv.interval_start for iv in intervals if float(iv.production_wh or 0) == peak),
        None,
    )

    row = DailySummary(
        system_id=system_id,
        day=day,
        production_kwh=Decimal(str(round(total_wh / 1000, 3))),
        peak_power_w=Decimal(str(round(peak * 4, 1))),
        peak_power_at=peak_at,
        interval_count=len(intervals),
        is_complete=len(intervals) >= 88,
    )
    await session.merge(row)
    await session.commit()
    logger.info("Daily summary built for system={} day={} kwh={}", system_id, day, row.production_kwh)
    return row


async def build_monthly_summary(
    session: AsyncSession,
    system_id: int,
    month: date,
    system: System,
) -> MonthlySummary:
    """Compute monthly PR and expected PR, upsert into monthly_summaries.

    Args:
        session: Active async database session.
        system_id: System to summarize.
        month: First day of the month to summarize.
        system: System ORM instance for size and install date.

    Returns:
        The upserted MonthlySummary instance.
    """
    from calendar import monthrange

    _, last_day = monthrange(month.year, month.month)
    month_end = date(month.year, month.month, last_day)

    daily_stmt = select(DailySummary).where(
        DailySummary.system_id == system_id,
        DailySummary.day >= month,
        DailySummary.day <= month_end,
    )
    daily_result = await session.execute(daily_stmt)
    daily_rows = daily_result.scalars().all()
    production_kwh = Decimal(str(sum(float(r.production_kwh or 0) for r in daily_rows)))

    irr_stmt = select(Irradiance).where(
        Irradiance.system_id == system_id,
        Irradiance.day >= month,
        Irradiance.day <= month_end,
    )
    irr_result = await session.execute(irr_stmt)
    irr_rows = irr_result.scalars().all()
    total_poa = sum(float(r.poa_kwh_m2 or 0) for r in irr_rows)

    system_size = float(system.system_size_kw or 0)
    theoretical_kwh = Decimal(str(round(system_size * total_poa, 3))) if total_poa else None

    performance_ratio = None
    if theoretical_kwh and float(theoretical_kwh) > 0:
        performance_ratio = Decimal(str(round(float(production_kwh) / float(theoretical_kwh), 4)))

    years_since_install = (month - system.install_date).days / 365.25 if system.install_date else 0
    deg_rate = float(system.degradation_rate or 0) / 100
    expected_pr = Decimal(str(round((1 - deg_rate) ** years_since_install, 4)))

    is_anomaly = False
    anomaly_reason = None
    if performance_ratio and expected_pr:
        drop = float(expected_pr) - float(performance_ratio)
        if drop > 0.015:
            is_anomaly = True
            anomaly_reason = f"PR {float(performance_ratio):.1%} is {drop:.1%} below expected {float(expected_pr):.1%}"

    row = MonthlySummary(
        system_id=system_id,
        month=month,
        production_kwh=production_kwh,
        theoretical_kwh=theoretical_kwh,
        performance_ratio=performance_ratio,
        expected_pr=expected_pr,
        is_anomaly=is_anomaly,
        anomaly_reason=anomaly_reason,
    )
    await session.merge(row)
    await session.commit()
    logger.info("Monthly summary built for system={} month={} PR={}", system_id, month, performance_ratio)
    return row
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
uv run pytest tests/unit/test_summarizer.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/helio/analytics/summarizer.py backend/tests/unit/test_summarizer.py
git commit -m "feat(analytics): add daily and monthly summarizer with PR calculation"
```

---

### Task 11: Degradation and anomaly analytics

**Files:**
- Create: `backend/helio/analytics/degradation.py`
- Create: `backend/tests/unit/test_degradation.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/unit/test_degradation.py`:

```python
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.analytics.degradation import calculate_annual_degradation, estimate_lost_production


@pytest.mark.asyncio
async def test_calculate_annual_degradation_two_years():
    mock_session = AsyncMock()

    monthly_rows = [
        MagicMock(month=date(2023, m, 1), performance_ratio=Decimal("0.82")) for m in range(1, 13)
    ] + [
        MagicMock(month=date(2024, m, 1), performance_ratio=Decimal("0.80")) for m in range(1, 5)
    ]

    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=monthly_rows)))
        )
    )

    result = await calculate_annual_degradation(mock_session, system_id=1)
    assert 2023 in result
    assert result[2023]["avg_pr"] == pytest.approx(0.82, rel=1e-3)


@pytest.mark.asyncio
async def test_estimate_lost_production_returns_kwh_and_dollars():
    mock_session = AsyncMock()

    monthly_rows = [
        MagicMock(
            month=date(2024, 4, 1),
            production_kwh=Decimal("400"),
            performance_ratio=Decimal("0.78"),
            expected_pr=Decimal("0.82"),
        )
    ]

    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=monthly_rows)))
        )
    )

    result = await estimate_lost_production(mock_session, system_id=1, rate_per_kwh=0.15)
    assert result["lost_kwh"] > 0
    assert result["lost_dollars"] > 0
    assert result["lost_dollars"] == pytest.approx(result["lost_kwh"] * 0.15, rel=1e-3)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/unit/test_degradation.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `backend/helio/analytics/degradation.py`**

```python
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.db.models import MonthlySummary


async def calculate_annual_degradation(
    session: AsyncSession,
    system_id: int,
) -> dict[int, dict]:
    """Compute average annual Performance Ratio and year-over-year drop.

    Args:
        session: Active async database session.
        system_id: System to analyze.

    Returns:
        Dict keyed by year with 'avg_pr' and 'annual_drop' (vs prior year).
    """
    stmt = select(MonthlySummary).where(
        MonthlySummary.system_id == system_id,
        MonthlySummary.performance_ratio.is_not(None),
    ).order_by(MonthlySummary.month)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    by_year: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        by_year[row.month.year].append(float(row.performance_ratio))

    output = {}
    prev_avg = None
    for year in sorted(by_year):
        avg_pr = sum(by_year[year]) / len(by_year[year])
        output[year] = {
            "avg_pr": round(avg_pr, 4),
            "annual_drop": round(prev_avg - avg_pr, 4) if prev_avg is not None else None,
        }
        prev_avg = avg_pr
    return output


async def estimate_lost_production(
    session: AsyncSession,
    system_id: int,
    rate_per_kwh: float = 0.15,
) -> dict[str, float]:
    """Estimate total production lost due to degradation below expected PR.

    Args:
        session: Active async database session.
        system_id: System to analyze.
        rate_per_kwh: Electricity rate in dollars per kWh for dollar estimate.

    Returns:
        Dict with 'lost_kwh' and 'lost_dollars'.
    """
    stmt = select(MonthlySummary).where(
        MonthlySummary.system_id == system_id,
        MonthlySummary.performance_ratio.is_not(None),
        MonthlySummary.expected_pr.is_not(None),
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    total_lost_kwh = 0.0
    for row in rows:
        pr = float(row.performance_ratio)
        expected = float(row.expected_pr)
        production = float(row.production_kwh or 0)
        if expected > 0 and pr < expected:
            lost_fraction = (expected - pr) / expected
            total_lost_kwh += production * lost_fraction

    return {
        "lost_kwh": round(total_lost_kwh, 1),
        "lost_dollars": round(total_lost_kwh * rate_per_kwh, 2),
    }
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
uv run pytest tests/unit/test_degradation.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/helio/analytics/degradation.py backend/tests/unit/test_degradation.py
git commit -m "feat(analytics): add degradation and lost production estimator"
```

---

## Phase 6 — FastAPI Backend

### Task 12: Pydantic response schemas

**Files:**
- Create: `backend/helio/api/schemas/overview.py`
- Create: `backend/helio/api/schemas/efficiency.py`
- Create: `backend/helio/api/schemas/settings.py`

- [ ] **Step 1: Write `backend/helio/api/schemas/overview.py`**

```python
from datetime import date

from pydantic import BaseModel


class ComparisonPair(BaseModel):
    current_kwh: float
    prior_kwh: float | None
    pct_change: float | None


class OverviewResponse(BaseModel):
    today: date
    today_kwh: float
    current_power_w: float | None
    day_comparison: ComparisonPair
    month_comparison: ComparisonPair
    ytd_comparison: ComparisonPair
    best_day_kwh: float | None
    best_day_date: date | None
    all_time_kwh: float
```

- [ ] **Step 2: Write `backend/helio/api/schemas/efficiency.py`**

```python
from datetime import date

from pydantic import BaseModel


class MonthlyPRPoint(BaseModel):
    month: date
    production_kwh: float
    performance_ratio: float | None
    expected_pr: float | None
    is_anomaly: bool


class DegradationSummary(BaseModel):
    annual_rates: dict[int, dict]
    lost_kwh: float
    lost_dollars: float
    warranty_threshold: float
    exceeds_warranty: bool


class EfficiencyResponse(BaseModel):
    pr_history: list[MonthlyPRPoint]
    degradation: DegradationSummary
```

- [ ] **Step 3: Write `backend/helio/api/schemas/settings.py`**

```python
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    enphase_system_id: str
    name: str | None
    location: str | None
    system_size_kw: Decimal | None
    panel_count: int | None
    panel_wattage_w: int | None
    install_date: date
    tilt_angle_deg: Decimal | None
    azimuth_deg: Decimal | None
    degradation_rate: Decimal
    irradiance_source: str

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    system_size_kw: Decimal | None = None
    panel_count: int | None = None
    panel_wattage_w: int | None = None
    install_date: date | None = None
    tilt_angle_deg: Decimal | None = None
    azimuth_deg: Decimal | None = None
    degradation_rate: Decimal | None = None
    irradiance_source: str | None = None
```

- [ ] **Step 4: Commit**

```bash
git add backend/helio/api/schemas/
git commit -m "feat(api): add Pydantic response schemas for all endpoints"
```

---

### Task 13: FastAPI routes

**Files:**
- Create: `backend/helio/api/routes/overview.py`
- Create: `backend/helio/api/routes/efficiency.py`
- Create: `backend/helio/api/routes/settings.py`
- Create: `backend/helio/api/main.py`
- Create: `backend/tests/integration/test_api.py`

- [ ] **Step 1: Write `backend/helio/api/routes/overview.py`**

```python
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.overview import ComparisonPair, OverviewResponse
from helio.db.models import DailySummary, EnergyInterval, System
from helio.db.session import get_db

router = APIRouter()


def _pct_change(current: float, prior: float | None) -> float | None:
    if prior is None or prior == 0:
        return None
    return round((current - prior) / prior * 100, 1)


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(db: AsyncSession = Depends(get_db)) -> OverviewResponse:
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        return OverviewResponse(
            today=date.today(),
            today_kwh=0.0,
            current_power_w=None,
            day_comparison=ComparisonPair(current_kwh=0.0, prior_kwh=None, pct_change=None),
            month_comparison=ComparisonPair(current_kwh=0.0, prior_kwh=None, pct_change=None),
            ytd_comparison=ComparisonPair(current_kwh=0.0, prior_kwh=None, pct_change=None),
            best_day_kwh=None,
            best_day_date=None,
            all_time_kwh=0.0,
        )

    today = date.today()
    same_day_lyr = today - timedelta(days=365)
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    async def get_day_kwh(d: date) -> float:
        row = (await db.execute(
            select(DailySummary).where(DailySummary.system_id == system.id, DailySummary.day == d)
        )).scalar_one_or_none()
        return float(row.production_kwh or 0) if row else 0.0

    async def get_period_kwh(start: date, end: date) -> float:
        result = await db.execute(
            select(func.sum(DailySummary.production_kwh)).where(
                DailySummary.system_id == system.id,
                DailySummary.day >= start,
                DailySummary.day <= end,
            )
        )
        return float(result.scalar() or 0)

    today_kwh = await get_day_kwh(today)
    lyr_day_kwh = await get_day_kwh(same_day_lyr)
    this_month = await get_period_kwh(month_start, today)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month = await get_period_kwh(last_month_start, last_month_end)
    this_ytd = await get_period_kwh(year_start, today)
    last_ytd = await get_period_kwh(year_start.replace(year=year_start.year - 1), same_day_lyr)

    best = (await db.execute(
        select(DailySummary).where(DailySummary.system_id == system.id).order_by(
            DailySummary.production_kwh.desc()
        ).limit(1)
    )).scalar_one_or_none()

    all_time_result = await db.execute(
        select(func.sum(DailySummary.production_kwh)).where(DailySummary.system_id == system.id)
    )
    all_time_kwh = float(all_time_result.scalar() or 0)

    return OverviewResponse(
        today=today,
        today_kwh=today_kwh,
        current_power_w=None,
        day_comparison=ComparisonPair(
            current_kwh=today_kwh,
            prior_kwh=lyr_day_kwh if lyr_day_kwh else None,
            pct_change=_pct_change(today_kwh, lyr_day_kwh),
        ),
        month_comparison=ComparisonPair(
            current_kwh=this_month,
            prior_kwh=last_month if last_month else None,
            pct_change=_pct_change(this_month, last_month),
        ),
        ytd_comparison=ComparisonPair(
            current_kwh=this_ytd,
            prior_kwh=last_ytd if last_ytd else None,
            pct_change=_pct_change(this_ytd, last_ytd),
        ),
        best_day_kwh=float(best.production_kwh) if best else None,
        best_day_date=best.day if best else None,
        all_time_kwh=all_time_kwh,
    )
```

- [ ] **Step 2: Write `backend/helio/api/routes/efficiency.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.analytics.degradation import calculate_annual_degradation, estimate_lost_production
from helio.api.schemas.efficiency import DegradationSummary, EfficiencyResponse, MonthlyPRPoint
from helio.db.models import MonthlySummary, System
from helio.db.session import get_db

router = APIRouter()

WARRANTY_THRESHOLD = 0.007


@router.get("/efficiency", response_model=EfficiencyResponse)
async def get_efficiency(db: AsyncSession = Depends(get_db)) -> EfficiencyResponse:
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        return EfficiencyResponse(
            pr_history=[],
            degradation=DegradationSummary(
                annual_rates={},
                lost_kwh=0.0,
                lost_dollars=0.0,
                warranty_threshold=WARRANTY_THRESHOLD * 100,
                exceeds_warranty=False,
            ),
        )

    monthly = (await db.execute(
        select(MonthlySummary).where(MonthlySummary.system_id == system.id).order_by(MonthlySummary.month)
    )).scalars().all()

    pr_history = [
        MonthlyPRPoint(
            month=row.month,
            production_kwh=float(row.production_kwh or 0),
            performance_ratio=float(row.performance_ratio) if row.performance_ratio else None,
            expected_pr=float(row.expected_pr) if row.expected_pr else None,
            is_anomaly=row.is_anomaly,
        )
        for row in monthly
    ]

    annual_rates = await calculate_annual_degradation(db, system.id)
    lost = await estimate_lost_production(db, system.id)

    recent_years = sorted(annual_rates.keys())[-2:]
    exceeds = False
    if len(recent_years) == 2:
        drop = annual_rates[recent_years[-1]].get("annual_drop") or 0
        exceeds = drop > WARRANTY_THRESHOLD

    return EfficiencyResponse(
        pr_history=pr_history,
        degradation=DegradationSummary(
            annual_rates=annual_rates,
            lost_kwh=lost["lost_kwh"],
            lost_dollars=lost["lost_dollars"],
            warranty_threshold=WARRANTY_THRESHOLD * 100,
            exceeds_warranty=exceeds,
        ),
    )
```

- [ ] **Step 3: Write `backend/helio/api/routes/settings.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helio.api.schemas.settings import SettingsResponse, SettingsUpdate
from helio.db.models import System
from helio.db.session import get_db

router = APIRouter()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)) -> SettingsResponse:
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="No system configured")
    return SettingsResponse.model_validate(system)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    system = (await db.execute(select(System).limit(1))).scalar_one_or_none()
    if system is None:
        raise HTTPException(status_code=404, detail="No system configured")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(system, field, value)

    await db.commit()
    await db.refresh(system)
    return SettingsResponse.model_validate(system)
```

- [ ] **Step 4: Write `backend/helio/api/main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from helio.api.routes.efficiency import router as efficiency_router
from helio.api.routes.overview import router as overview_router
from helio.api.routes.settings import router as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Helio Monitor API starting")
    yield
    logger.info("Helio Monitor API shutting down")


app = FastAPI(title="Helio Monitor API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(overview_router, prefix="/api")
app.include_router(efficiency_router, prefix="/api")
app.include_router(settings_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 5: Write integration tests**

`backend/tests/integration/test_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from helio.api.main import app


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_overview_returns_200_with_no_system():
    with patch("helio.api.routes.overview.get_db") as mock_db:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        mock_db.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/overview")
    assert response.status_code == 200
    data = response.json()
    assert "today_kwh" in data


@pytest.mark.asyncio
async def test_settings_404_with_no_system():
    with patch("helio.api.routes.settings.get_db") as mock_db:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        mock_db.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/settings")
    assert response.status_code == 404
```

- [ ] **Step 6: Run the integration tests**

```bash
cd backend
uv run pytest tests/integration/test_api.py -v
```

Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add backend/helio/api/ backend/tests/integration/
git commit -m "feat(api): add FastAPI routes for overview, efficiency, settings, and health"
```

---

## Phase 7 — Frontend Integration

### Task 14: Typed API client and data hooks

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/hooks/useOverview.ts`
- Create: `frontend/src/hooks/useEfficiency.ts`
- Create: `frontend/src/hooks/useSettings.ts`

- [ ] **Step 1: Write `frontend/src/api/client.ts`**

```typescript
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export interface ComparisonPair {
  current_kwh: number;
  prior_kwh: number | null;
  pct_change: number | null;
}

export interface OverviewData {
  today: string;
  today_kwh: number;
  current_power_w: number | null;
  day_comparison: ComparisonPair;
  month_comparison: ComparisonPair;
  ytd_comparison: ComparisonPair;
  best_day_kwh: number | null;
  best_day_date: string | null;
  all_time_kwh: number;
}

export interface MonthlyPRPoint {
  month: string;
  production_kwh: number;
  performance_ratio: number | null;
  expected_pr: number | null;
  is_anomaly: boolean;
}

export interface EfficiencyData {
  pr_history: MonthlyPRPoint[];
  degradation: {
    annual_rates: Record<string, { avg_pr: number; annual_drop: number | null }>;
    lost_kwh: number;
    lost_dollars: number;
    warranty_threshold: number;
    exceeds_warranty: boolean;
  };
}

export interface SystemSettings {
  enphase_system_id: string;
  name: string | null;
  location: string | null;
  system_size_kw: string | null;
  panel_count: number | null;
  panel_wattage_w: number | null;
  install_date: string;
  tilt_angle_deg: string | null;
  azimuth_deg: string | null;
  degradation_rate: string;
  irradiance_source: string;
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  getOverview: () => apiFetch<OverviewData>("/api/overview"),
  getEfficiency: () => apiFetch<EfficiencyData>("/api/efficiency"),
  getSettings: () => apiFetch<SystemSettings>("/api/settings"),
  updateSettings: (data: Partial<SystemSettings>) =>
    apiFetch<SystemSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
};
```

- [ ] **Step 2: Write `frontend/src/hooks/useOverview.ts`**

```typescript
import { useEffect, useState } from "react";
import { api, OverviewData } from "../api/client";

export function useOverview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getOverview()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}
```

- [ ] **Step 3: Write `frontend/src/hooks/useEfficiency.ts`**

```typescript
import { useEffect, useState } from "react";
import { api, EfficiencyData } from "../api/client";

export function useEfficiency() {
  const [data, setData] = useState<EfficiencyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getEfficiency()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}
```

- [ ] **Step 4: Write `frontend/src/hooks/useSettings.ts`**

```typescript
import { useEffect, useState } from "react";
import { api, SystemSettings } from "../api/client";

export function useSettings() {
  const [data, setData] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function save(updates: Partial<SystemSettings>) {
    const updated = await api.updateSettings(updates);
    setData(updated);
    return updated;
  }

  useEffect(() => {
    api
      .getSettings()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error, save };
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/ frontend/src/hooks/
git commit -m "feat(frontend): add typed API client and data-fetching hooks"
```

---

### Task 15: React pages wired to live data

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/OverviewPage.tsx`
- Create: `frontend/src/pages/EfficiencyPage.tsx`
- Create: `frontend/src/pages/SetupPage.tsx`
- Create: `frontend/src/components/StatCard.tsx`
- Create: `frontend/src/components/ComparisonBar.tsx`

- [ ] **Step 1: Write `frontend/src/components/StatCard.tsx`**

```typescript
import clsx from "clsx";

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}

export function StatCard({ label, value, sub, highlight }: StatCardProps) {
  return (
    <div
      className={clsx(
        "rounded-xl p-5 flex flex-col gap-1",
        highlight ? "bg-solar-500/20 border border-solar-500/40" : "bg-gray-800/60 border border-gray-700"
      )}
    >
      <p className="text-xs text-gray-400 uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-semibold text-white">{value}</p>
      {sub && <p className="text-sm text-gray-400">{sub}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/components/ComparisonBar.tsx`**

```typescript
import clsx from "clsx";

interface ComparisonBarProps {
  label: string;
  current: number;
  prior: number | null;
  pctChange: number | null;
  unit?: string;
}

export function ComparisonBar({
  label,
  current,
  prior,
  pctChange,
  unit = "kWh",
}: ComparisonBarProps) {
  const positive = pctChange !== null && pctChange >= 0;
  return (
    <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5">
      <p className="text-xs text-gray-400 uppercase tracking-wider mb-3">{label}</p>
      <div className="flex items-end justify-between">
        <div>
          <span className="text-2xl font-semibold text-white">
            {current.toFixed(1)} {unit}
          </span>
          {prior !== null && (
            <span className="ml-2 text-sm text-gray-400">vs {prior.toFixed(1)}</span>
          )}
        </div>
        {pctChange !== null && (
          <span
            className={clsx(
              "text-sm font-medium px-2 py-1 rounded-md",
              positive ? "text-green-400 bg-green-400/10" : "text-red-400 bg-red-400/10"
            )}
          >
            {positive ? "+" : ""}
            {pctChange.toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write `frontend/src/pages/OverviewPage.tsx`**

```typescript
import { useOverview } from "../hooks/useOverview";
import { StatCard } from "../components/StatCard";
import { ComparisonBar } from "../components/ComparisonBar";

export function OverviewPage() {
  const { data, loading, error } = useOverview();

  if (loading) return <div className="text-gray-400 p-8">Loading...</div>;
  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Overview</h1>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Today"
          value={`${data.today_kwh.toFixed(1)} kWh`}
          sub={data.today}
          highlight
        />
        <StatCard
          label="All Time"
          value={`${(data.all_time_kwh / 1000).toFixed(1)} MWh`}
        />
        {data.best_day_kwh && (
          <StatCard
            label="Best Day"
            value={`${data.best_day_kwh.toFixed(1)} kWh`}
            sub={data.best_day_date ?? undefined}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ComparisonBar
          label="Today vs same day last year"
          current={data.day_comparison.current_kwh}
          prior={data.day_comparison.prior_kwh}
          pctChange={data.day_comparison.pct_change}
        />
        <ComparisonBar
          label="This month vs last month"
          current={data.month_comparison.current_kwh}
          prior={data.month_comparison.prior_kwh}
          pctChange={data.month_comparison.pct_change}
        />
        <ComparisonBar
          label="Year to date vs prior year"
          current={data.ytd_comparison.current_kwh}
          prior={data.ytd_comparison.prior_kwh}
          pctChange={data.ytd_comparison.pct_change}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write `frontend/src/pages/EfficiencyPage.tsx`**

```typescript
import { useEfficiency } from "../hooks/useEfficiency";
import { StatCard } from "../components/StatCard";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

export function EfficiencyPage() {
  const { data, loading, error } = useEfficiency();

  if (loading) return <div className="text-gray-400 p-8">Loading...</div>;
  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;
  if (!data) return null;

  const { degradation, pr_history } = data;
  const chartData = pr_history.map((p) => ({
    month: p.month.slice(0, 7),
    pr: p.performance_ratio !== null ? +(p.performance_ratio * 100).toFixed(1) : null,
    expected: p.expected_pr !== null ? +(p.expected_pr * 100).toFixed(1) : null,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Efficiency</h1>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Lost Production"
          value={`${degradation.lost_kwh.toFixed(0)} kWh`}
          sub={`$${degradation.lost_dollars.toFixed(0)} estimated`}
          highlight={degradation.exceeds_warranty}
        />
        <StatCard
          label="Warranty Threshold"
          value={`${degradation.warranty_threshold.toFixed(1)}%/yr`}
        />
        {degradation.exceeds_warranty && (
          <StatCard
            label="Status"
            value="Above Threshold"
            highlight
          />
        )}
      </div>

      <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5">
        <p className="text-sm text-gray-400 mb-4">Performance Ratio history (%)</p>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <XAxis dataKey="month" tick={{ fill: "#9ca3af", fontSize: 11 }} />
            <YAxis domain={[60, 100]} tick={{ fill: "#9ca3af", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1f2937", border: "none" }}
              labelStyle={{ color: "#f9fafb" }}
            />
            <Line
              type="monotone"
              dataKey="pr"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              name="Actual PR %"
            />
            <Line
              type="monotone"
              dataKey="expected"
              stroke="#6b7280"
              strokeWidth={1}
              strokeDasharray="4 4"
              dot={false}
              name="Expected PR %"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Write `frontend/src/pages/SetupPage.tsx`**

```typescript
import { useState } from "react";
import { useSettings } from "../hooks/useSettings";

export function SetupPage() {
  const { data, loading, error, save } = useSettings();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  if (loading) return <div className="text-gray-400 p-8">Loading...</div>;
  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;
  if (!data) return null;

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    setSaving(true);
    setSaveError(null);
    try {
      await save({
        name: fd.get("name") as string,
        location: fd.get("location") as string,
        system_size_kw: fd.get("system_size_kw") as string,
        panel_count: fd.get("panel_count") ? Number(fd.get("panel_count")) : null,
        panel_wattage_w: fd.get("panel_wattage_w") ? Number(fd.get("panel_wattage_w")) : null,
        install_date: fd.get("install_date") as string,
        tilt_angle_deg: fd.get("tilt_angle_deg") as string,
        azimuth_deg: fd.get("azimuth_deg") as string,
        degradation_rate: fd.get("degradation_rate") as string,
        irradiance_source: fd.get("irradiance_source") as string,
      });
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const field = (label: string, name: string, defaultValue: string | number | null, type = "text") => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-gray-400 uppercase tracking-wider">{label}</label>
      <input
        name={name}
        type={type}
        defaultValue={defaultValue ?? ""}
        className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-solar-500"
      />
    </div>
  );

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-white">Setup</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        {field("System Name", "name", data.name)}
        {field("Location", "location", data.location)}
        {field("System Size (kW)", "system_size_kw", data.system_size_kw, "number")}
        {field("Panel Count", "panel_count", data.panel_count, "number")}
        {field("Panel Wattage (W)", "panel_wattage_w", data.panel_wattage_w, "number")}
        {field("Install Date", "install_date", data.install_date, "date")}
        {field("Tilt Angle (deg)", "tilt_angle_deg", data.tilt_angle_deg, "number")}
        {field("Azimuth (deg)", "azimuth_deg", data.azimuth_deg, "number")}
        {field("Degradation Rate (%/yr)", "degradation_rate", data.degradation_rate, "number")}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-400 uppercase tracking-wider">Irradiance Source</label>
          <select
            name="irradiance_source"
            defaultValue={data.irradiance_source}
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
          >
            <option value="nrel">NREL</option>
            <option value="nasa">NASA POWER</option>
            <option value="manual">Manual (disabled)</option>
          </select>
        </div>
        {saveError && <p className="text-red-400 text-sm">{saveError}</p>}
        <button
          type="submit"
          disabled={saving}
          className="bg-solar-500 hover:bg-solar-600 disabled:opacity-50 text-white font-medium px-6 py-2 rounded-lg text-sm"
        >
          {saving ? "Saving..." : "Save Settings"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 6: Update `frontend/src/App.tsx` with navigation and pages**

```typescript
import { useState } from "react";
import { OverviewPage } from "./pages/OverviewPage";
import { EfficiencyPage } from "./pages/EfficiencyPage";
import { SetupPage } from "./pages/SetupPage";
import clsx from "clsx";

type Tab = "overview" | "efficiency" | "setup";

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "efficiency", label: "Efficiency" },
    { id: "setup", label: "Setup" },
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-8">
        <span className="text-solar-400 font-bold text-lg tracking-tight">Helio Monitor</span>
        <nav className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={clsx(
                "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                tab === t.id
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-white"
              )}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="px-6 py-8 max-w-6xl mx-auto">
        {tab === "overview" && <OverviewPage />}
        {tab === "efficiency" && <EfficiencyPage />}
        {tab === "setup" && <SetupPage />}
      </main>
    </div>
  );
}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): wire React pages to live API with Overview, Efficiency, Setup"
```

---

## Phase 8 — DevOps & Hardening

### Task 16: APScheduler integration and backfill script

**Files:**
- Create: `backend/helio/ingestion/scheduler.py`
- Create: `backend/scripts/backfill.py`

- [ ] **Step 1: Write `backend/helio/ingestion/scheduler.py`**

```python
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from helio.core.config import settings
from helio.db.models import System
from helio.db.session import AsyncSessionLocal
from helio.ingestion.enphase_client import EnphaseClient
from helio.ingestion.irradiance_client import NASAClient, NRELClient
from helio.ingestion.poller import poll_intervals, poll_irradiance
from helio.analytics.summarizer import build_daily_summary, build_monthly_summary

scheduler = AsyncIOScheduler(timezone=settings.tz)


async def _daily_poll() -> None:
    """Poll yesterday's intervals and irradiance, then rebuild summaries."""
    yesterday = date.today() - timedelta(days=1)
    logger.info("Daily poll starting for {}", yesterday)

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        system = (await session.execute(select(System).limit(1))).scalar_one_or_none()
        if system is None:
            logger.warning("No system found in DB — skipping poll")
            return

        client = EnphaseClient(
            client_id=settings.enphase_client_id,
            client_secret=settings.enphase_client_secret,
            system_id=settings.enphase_system_id,
            access_token="",
            refresh_token="",
            fernet_key=settings.fernet_key,
        )
        await client.refresh_access_token()
        await poll_intervals(session, client, system.id, yesterday, yesterday)

        if settings.irradiance_source == "nrel":
            irr_client = NRELClient(api_key=settings.nrel_api_key)
        else:
            irr_client = NASAClient()

        await poll_irradiance(
            session,
            irr_client,
            system.id,
            float(system.latitude or 0),
            float(system.longitude or 0),
            float(system.tilt_angle_deg or 30),
            float(system.azimuth_deg or 180),
            yesterday,
            settings.irradiance_source,
        )

        await build_daily_summary(session, system.id, yesterday)

        if yesterday.day == 1:
            prev_month = (yesterday.replace(day=1) - timedelta(days=1)).replace(day=1)
            await build_monthly_summary(session, system.id, prev_month, system)

    logger.info("Daily poll complete for {}", yesterday)


def start_scheduler() -> None:
    """Register and start the APScheduler cron jobs."""
    scheduler.add_job(
        _daily_poll,
        "cron",
        hour=settings.poll_hour,
        minute=settings.poll_minute,
        id="daily_poll",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — daily poll at {:02d}:{:02d} {}", settings.poll_hour, settings.poll_minute, settings.tz)
```

- [ ] **Step 2: Update `backend/helio/api/main.py` lifespan to start scheduler**

Replace the lifespan function:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from helio.api.routes.efficiency import router as efficiency_router
from helio.api.routes.overview import router as overview_router
from helio.api.routes.settings import router as settings_router
from helio.ingestion.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    logger.info("Helio Monitor API starting")
    yield
    logger.info("Helio Monitor API shutting down")


app = FastAPI(title="Helio Monitor API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(overview_router, prefix="/api")
app.include_router(efficiency_router, prefix="/api")
app.include_router(settings_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 3: Write `backend/scripts/backfill.py`**

```python
"""One-shot script to backfill all historical data from install date to today.

Usage:
    docker compose exec api python scripts/backfill.py
"""
import asyncio
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select

from helio.core.config import settings
from helio.db.models import System
from helio.db.session import AsyncSessionLocal
from helio.ingestion.enphase_client import EnphaseClient
from helio.ingestion.irradiance_client import NASAClient, NRELClient
from helio.ingestion.poller import detect_gaps, poll_intervals, poll_irradiance
from helio.analytics.summarizer import build_daily_summary, build_monthly_summary


async def backfill() -> None:
    async with AsyncSessionLocal() as session:
        system = (await session.execute(select(System).limit(1))).scalar_one_or_none()
        if system is None:
            logger.error("No system found. Configure your system in Setup first.")
            return

        client = EnphaseClient(
            client_id=settings.enphase_client_id,
            client_secret=settings.enphase_client_secret,
            system_id=settings.enphase_system_id,
            access_token="",
            refresh_token="",
            fernet_key=settings.fernet_key,
        )
        await client.refresh_access_token()

        irr_client = NRELClient(settings.nrel_api_key) if settings.irradiance_source == "nrel" else NASAClient()

        start = system.install_date
        end = date.today() - timedelta(days=1)
        gaps = await detect_gaps(session, system.id, start, end)
        logger.info("Backfill: {} days missing between {} and {}", len(gaps), start, end)

        for day in gaps:
            logger.info("Backfilling {}", day)
            await poll_intervals(session, client, system.id, day, day)
            await poll_irradiance(
                session,
                irr_client,
                system.id,
                float(system.latitude or 0),
                float(system.longitude or 0),
                float(system.tilt_angle_deg or 30),
                float(system.azimuth_deg or 180),
                day,
                settings.irradiance_source,
            )
            await build_daily_summary(session, system.id, day)
            await asyncio.sleep(0.5)  # respect API rate limits

        logger.info("Backfill complete")


if __name__ == "__main__":
    asyncio.run(backfill())
```

- [ ] **Step 4: Run health check to confirm scheduler boots without error**

```bash
cd backend
uv run pytest tests/integration/test_api.py::test_health_check -v
```

Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/helio/ingestion/scheduler.py backend/scripts/ backend/helio/api/main.py
git commit -m "feat(ingestion): add APScheduler daily poll and backfill script"
```

---

## Phase 9 — Final Validation

### Task 17: Full test run and docker compose smoke test

**Files:**
- No new files — validation only.

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend
uv run pytest tests/ -v --tb=short
```

Expected: all tests pass, 0 failures.

- [ ] **Step 2: Run the linter**

```bash
uv run ruff check helio/
uv run ruff format --check helio/
```

Fix any issues before proceeding.

- [ ] **Step 3: Start the stack with docker compose**

```bash
cd /path/to/repo   # repo root
docker compose up -d --build
```

Expected: all 3 services start (db, api, frontend).

- [ ] **Step 4: Run migrations inside the container**

```bash
make migrate
```

Expected: `INFO [alembic] Running upgrade -> 001..., initial_schema`

- [ ] **Step 5: Verify the API health endpoint**

```bash
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 6: Verify the frontend loads**

Open `http://localhost:3000` in a browser. The Helio Monitor header and tabs should render. Overview/Efficiency pages show zeros (no data yet). Setup page shows 404 (no system configured).

- [ ] **Step 7: Seed a system record and verify overview responds**

```bash
docker compose exec db psql -U helio -d helio -c "
INSERT INTO systems (enphase_system_id, install_date, degradation_rate)
VALUES ('test-001', '2023-01-01', 0.5)
ON CONFLICT DO NOTHING;
"
curl http://localhost:8000/api/overview
```

Expected: JSON with `today_kwh`, `all_time_kwh`, comparison fields.

- [ ] **Step 8: Commit final state**

```bash
git add -A
git commit -m "chore: final validation — all tests pass, stack healthy"
```

---

## Self-Review Checklist

**Spec coverage:**
- BR-01 (daily poll) → Task 9 + Task 16 (scheduler)
- BR-02 (token refresh) → Task 7 (EnphaseClient.refresh_access_token)
- BR-03 (gap detection / backfill) → Task 9 (detect_gaps, poll_intervals) + Task 16 (backfill.py)
- BR-04 (irradiance) → Task 8
- BR-05/06/07/08 (historical comparisons) → Task 13 (overview route)
- BR-09/10/11/12 (PR, trend, anomaly) → Task 10 + Task 13 (efficiency route)
- BR-13/14 (degradation rate, warranty) → Task 11 + Task 13
- BR-15/16 (panel heatmap) → out of scope for MVP (panel data requires Watt plan upgrade, noted in BRD risk register)
- BR-17/18/19/20 (Setup UI) → Task 12 + Task 13 (settings route) + Task 15 (SetupPage)
- BR-21 through BR-26 (distribution docs) → Phase 10 per dev-plan.md (not in this plan)

**Placeholder scan:** None found.

**Type consistency:**
- `IntervalData` defined in Task 7, used in Task 9 — consistent.
- `OverviewResponse`, `ComparisonPair` defined in Task 12, used in Task 13 — consistent.
- `EfficiencyResponse`, `MonthlyPRPoint` defined in Task 12, used in Task 13 — consistent.
- `SettingsResponse`, `SettingsUpdate` defined in Task 12, used in Task 13 — consistent.
- `useOverview`, `useEfficiency`, `useSettings` return types match API client types — consistent.
- `build_daily_summary`, `build_monthly_summary` signatures in Task 10 match calls in Task 16 — consistent.
- `detect_gaps`, `poll_intervals`, `poll_irradiance` signatures in Task 9 match calls in Task 16 — consistent.
