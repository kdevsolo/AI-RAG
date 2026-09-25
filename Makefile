.DEFAULT_GOAL := help

# Load .env (if present) so recipes can use $(POSTGRES_USER) etc.
-include .env
export

APP        := app.main:app
APP_DIR    := src
HOST       ?= 127.0.0.1
PORT       ?= 8000

.PHONY: help install dev run lint format typecheck test check \
        pre-commit-install pre-commit \
        db-up db-down db-reset db-shell migration migrate downgrade \
        worker temporal-up

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Sync all dependencies (incl. dev group)
	uv sync

pre-commit-install: ## Install the git pre-commit hook
	uv run pre-commit install

pre-commit: ## Run pre-commit hooks against all files
	uv run pre-commit run --all-files

dev: ## Run with autoreload for local development
	uv run uvicorn $(APP) --app-dir $(APP_DIR) --host $(HOST) --port $(PORT) --reload

run: ## Run without autoreload
	uv run uvicorn $(APP) --app-dir $(APP_DIR) --host $(HOST) --port $(PORT)

lint: ## Lint with ruff
	uv run ruff check .

format: ## Format with ruff
	uv run ruff format .

typecheck: ## Type-check with mypy
	uv run mypy $(APP_DIR)

test: ## Run the test suite
	uv run pytest

check: lint typecheck test ## Run lint, typecheck, and tests

db-up: ## Start the local Postgres container
	docker compose up -d

db-down: ## Stop the Postgres container (data is kept)
	docker compose down

db-reset: ## Stop Postgres and delete its data volume
	docker compose down -v

db-shell: ## Open a psql shell inside the container
	docker compose exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

migration: ## Autogenerate a migration: make migration m="create users table"
	uv run alembic revision --autogenerate -m "$(m)"

migrate: ## Apply all pending migrations
	uv run alembic upgrade head

downgrade: ## Roll back the most recent migration
	uv run alembic downgrade -1

worker: ## Run the Temporal ingestion worker
	PYTHONPATH=$(APP_DIR) uv run python -m app.temporal.worker

temporal-up: ## Start Temporal server + UI (http://localhost:8080)
	docker compose up -d temporal-db temporal temporal-ui
