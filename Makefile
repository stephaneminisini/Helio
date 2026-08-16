# ─────────────────────────────────────────────────────────────────────────────
# Helio Monitor — Makefile
# ─────────────────────────────────────────────────────────────────────────────

COMPOSE     = docker compose
API_SERVICE = api
DB_SERVICE  = db
BACKUP_DIR  = ./backups
TIMESTAMP   = $(shell date +%Y%m%d_%H%M%S)

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help message
	@echo ""
	@echo "  ☀️  Helio Monitor"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Core Services ─────────────────────────────────────────────────────────────

.PHONY: up
up: ## Start all services (build if needed)
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  ✅  Helio Monitor is running"
	@echo "  Dashboard → http://localhost:3000"
	@echo "  API Docs  → http://localhost:8000/docs"
	@echo ""

.PHONY: down
down: ## Stop all services (data preserved)
	$(COMPOSE) down

.PHONY: down-full
down-full: ## Stop all services AND delete all data ⚠️
	@echo "⚠️  This will delete all data. Press Ctrl+C to cancel, or Enter to continue."
	@read _
	$(COMPOSE) down -v

.PHONY: restart
restart: ## Restart all services
	$(COMPOSE) restart

.PHONY: restart-api
restart-api: ## Restart API service only
	$(COMPOSE) restart $(API_SERVICE)

.PHONY: build
build: ## Rebuild all Docker images without cache
	$(COMPOSE) build --no-cache

.PHONY: status
status: ## Show container health status
	$(COMPOSE) ps

# ── Database ──────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate: ## Run Alembic database migrations
	$(COMPOSE) exec $(API_SERVICE) alembic upgrade head
	@echo "✅  Migrations complete"

.PHONY: migrate-create
migrate-create: ## Create a new migration (usage: make migrate-create MSG="add column")
	$(COMPOSE) exec $(API_SERVICE) alembic revision --autogenerate -m "$(MSG)"

.PHONY: migrate-down
migrate-down: ## Roll back the last migration
	$(COMPOSE) exec $(API_SERVICE) alembic downgrade -1

.PHONY: migrate-history
migrate-history: ## Show migration history
	$(COMPOSE) exec $(API_SERVICE) alembic history --verbose

.PHONY: psql
psql: ## Open a psql shell in the database container
	$(COMPOSE) exec $(DB_SERVICE) psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

# ── Data ──────────────────────────────────────────────────────────────────────

.PHONY: backfill
backfill: ## Fetch all historical data from install date to today
	@echo "⏳  Starting backfill — this may take several minutes..."
	$(COMPOSE) exec $(API_SERVICE) python -m helio.cli backfill
	@echo "✅  Backfill complete"

.PHONY: poll-now
poll-now: ## Trigger an immediate poll (don't wait for scheduled time)
	$(COMPOSE) exec $(API_SERVICE) python -m helio.cli poll-now
	@echo "✅  Poll complete"

.PHONY: poll-status
poll-status: ## Show the last 10 poll run results
	$(COMPOSE) exec $(API_SERVICE) python -m helio.cli poll-status

.PHONY: rebuild-summaries
rebuild-summaries: ## Rebuild all daily and monthly summaries from raw intervals
	@echo "⏳  Rebuilding summaries..."
	$(COMPOSE) exec $(API_SERVICE) python -m helio.cli rebuild-summaries
	@echo "✅  Summaries rebuilt"

.PHONY: seed-mock
seed-mock: ## Insert 3 years of synthetic data for development (no Enphase account needed)
	@echo "⏳  Seeding mock data..."
	$(COMPOSE) exec $(API_SERVICE) python -m helio.cli seed-mock
	@echo "✅  Mock data seeded — open http://localhost:3000"

# ── Backup & Restore ──────────────────────────────────────────────────────────

.PHONY: backup-db
backup-db: ## Dump the database to ./backups/
	@mkdir -p $(BACKUP_DIR)
	$(COMPOSE) exec -T $(DB_SERVICE) pg_dump \
		-U $${POSTGRES_USER} $${POSTGRES_DB} \
		> $(BACKUP_DIR)/helio_$(TIMESTAMP).dump
	@echo "✅  Backup saved to $(BACKUP_DIR)/helio_$(TIMESTAMP).dump"

.PHONY: restore-db
restore-db: ## Restore from the latest backup in ./backups/
	$(eval LATEST := $(shell ls -t $(BACKUP_DIR)/*.dump 2>/dev/null | head -1))
	@if [ -z "$(LATEST)" ]; then echo "❌  No backup files found in $(BACKUP_DIR)"; exit 1; fi
	@echo "Restoring from $(LATEST) — press Ctrl+C to cancel, or Enter to continue."
	@read _
	$(COMPOSE) exec -T $(DB_SERVICE) psql \
		-U $${POSTGRES_USER} $${POSTGRES_DB} < $(LATEST)
	@echo "✅  Restore complete from $(LATEST)"

# ── Logs ──────────────────────────────────────────────────────────────────────

.PHONY: logs
logs: ## Tail logs from all services
	$(COMPOSE) logs -f

.PHONY: logs-api
logs-api: ## Tail API logs only
	$(COMPOSE) logs -f $(API_SERVICE)

.PHONY: logs-db
logs-db: ## Tail database logs only
	$(COMPOSE) logs -f $(DB_SERVICE)

# ── Development ───────────────────────────────────────────────────────────────

.PHONY: shell
shell: ## Open a bash shell in the API container
	$(COMPOSE) exec $(API_SERVICE) bash

.PHONY: test
test: ## Run the full test suite
	$(COMPOSE) exec $(API_SERVICE) pytest tests/ -v --tb=short

.PHONY: test-unit
test-unit: ## Run unit tests only
	$(COMPOSE) exec $(API_SERVICE) pytest tests/unit/ -v --tb=short

.PHONY: test-integration
test-integration: ## Run integration tests only
	$(COMPOSE) exec $(API_SERVICE) pytest tests/integration/ -v --tb=short

.PHONY: test-coverage
test-coverage: ## Run tests with coverage report
	$(COMPOSE) exec $(API_SERVICE) pytest tests/ --cov=helio --cov-report=term-missing

.PHONY: lint
lint: ## Format and lint with ruff
	$(COMPOSE) exec $(API_SERVICE) uv run ruff format helio/ tests/
	$(COMPOSE) exec $(API_SERVICE) uv run ruff check helio/ tests/

.PHONY: lint-check
lint-check: ## Check formatting and lint without making changes (for CI)
	$(COMPOSE) exec $(API_SERVICE) uv run ruff format --check helio/ tests/
	$(COMPOSE) exec $(API_SERVICE) uv run ruff check helio/ tests/

# ── Updates ───────────────────────────────────────────────────────────────────

.PHONY: update
update: ## Pull latest code + images, run migrations, restart
	git pull
	$(COMPOSE) pull
	$(COMPOSE) build
	$(MAKE) migrate
	$(COMPOSE) up -d
	@echo "✅  Helio Monitor updated and restarted"

# ── System ────────────────────────────────────────────────────────────────────

.PHONY: enable-autostart
enable-autostart: ## Install systemd service to start on boot (Linux)
	@echo "[Unit]" > /tmp/helio-monitor.service
	@echo "Description=Helio Monitor" >> /tmp/helio-monitor.service
	@echo "After=docker.service" >> /tmp/helio-monitor.service
	@echo "Requires=docker.service" >> /tmp/helio-monitor.service
	@echo "" >> /tmp/helio-monitor.service
	@echo "[Service]" >> /tmp/helio-monitor.service
	@echo "Type=oneshot" >> /tmp/helio-monitor.service
	@echo "RemainAfterExit=yes" >> /tmp/helio-monitor.service
	@echo "WorkingDirectory=$(CURDIR)" >> /tmp/helio-monitor.service
	@echo "ExecStart=$(COMPOSE) up -d" >> /tmp/helio-monitor.service
	@echo "ExecStop=$(COMPOSE) down" >> /tmp/helio-monitor.service
	@echo "" >> /tmp/helio-monitor.service
	@echo "[Install]" >> /tmp/helio-monitor.service
	@echo "WantedBy=multi-user.target" >> /tmp/helio-monitor.service
	sudo mv /tmp/helio-monitor.service /etc/systemd/system/helio-monitor.service
	sudo systemctl daemon-reload
	sudo systemctl enable helio-monitor
	@echo "✅  Autostart enabled — Helio Monitor will start on boot"

.PHONY: disable-autostart
disable-autostart: ## Remove systemd autostart service
	sudo systemctl disable helio-monitor
	sudo rm -f /etc/systemd/system/helio-monitor.service
	sudo systemctl daemon-reload
	@echo "✅  Autostart disabled"

.PHONY: generate-fernet-key
generate-fernet-key: ## Generate a new Fernet encryption key for .env
	@python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ── Setup Helpers ─────────────────────────────────────────────────────────────

.PHONY: init
init: ## First-time setup: copy .env.example, generate key, start, migrate
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "📝  Created .env from .env.example"; \
		FERNET=$$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"); \
		sed -i.bak "s|^FERNET_KEY=.*|FERNET_KEY=$$FERNET|" .env && rm -f .env.bak; \
		echo "🔑  Generated and set FERNET_KEY in .env"; \
		echo ""; \
		echo "👉  Now edit .env and fill in:"; \
		echo "    - ENPHASE_CLIENT_ID"; \
		echo "    - ENPHASE_CLIENT_SECRET"; \
		echo "    - ENPHASE_SYSTEM_ID"; \
		echo "    - POSTGRES_PASSWORD"; \
		echo "    - TZ (your timezone)"; \
		echo ""; \
		echo "Then run: make up && make migrate && make backfill"; \
	else \
		echo "⚠️  .env already exists — skipping init"; \
	fi
