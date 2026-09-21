# CLAUDE.md

This is a python fastapi API project which has the capability to manage users and make REST api calls.

## Commands

This project uses `uv` for dependency management and a `Makefile` for common tasks.

```
make install         # uv sync (installs dev group too)
make dev              # run with autoreload (uvicorn, src/app/main.py:app)
make run              # run without autoreload
make lint             # ruff check .
make format           # ruff format .
make typecheck        # mypy src
make test             # pytest
make check            # lint + typecheck + test

make db-up            # start local Postgres via docker-compose
make db-down          # stop Postgres (keeps data volume)
make db-reset         # stop Postgres and delete its data volume
make db-shell         # psql shell inside the container

make migration m="create users table"   # alembic revision --autogenerate -m "..."
make migrate                            # alembic upgrade head
make downgrade                          # alembic downgrade -1
```

Run a single test with `uv run pytest tests/test_smoke.py::test_health`.

`test_health_db` requires Postgres to be running (`make db-up`); config is read from `.env` (copy `.env.example` first).

Pre-commit hooks (ruff check --fix, ruff format) can be installed with `make pre-commit-install` and run manually with `make pre-commit`.

## Architecture

Standard `src/` layout FastAPI app (`pyproject.toml` sets `pythonpath = ["src"]` for pytest, and the Makefile passes `--app-dir src` to uvicorn), so imports are always `from app...`, never `from src.app...`.

Request flow: **routes → service → db model**, with schemas for request/response validation in between.

- `app/main.py` — FastAPI app instance, includes routers, has raw `/health` and `/health/db` checks.
- `app/api/routes/` — APIRouter modules. Route handlers depend on a per-request service instance built via a local `get_user_service` factory (see `user_routes.py`), which itself depends on `DbSession` (see below). Keep this pattern for new resource routers: a small `get_<x>_service` factory + `Annotated` dependency alias.
- `app/services/` — business logic, one class per resource, takes a `Session` in `__init__`. No `db.close()` here — that's owned by the request-scoped dependency.
- `app/db/deps.py` — `get_db()` yields a `Session` from `SessionLocal` and closes it after the request; exposed as the `DbSession` annotated type for use in FastAPI `Depends`.
- `app/db/session.py` — engine/`SessionLocal` construction from `config.database_url`.
- `app/db/base.py` — declarative `Base` with a shared naming convention for constraints/indexes (important: Alembic autogenerate relies on this for consistent constraint names), plus a `TimestampMixin` (`created_at`/`updated_at` server defaults).
- `app/db/models.py` — SQLAlchemy ORM models, inherit from `Base` (+ `TimestampMixin` where relevant).
- `app/schema/` — Pydantic v2 schemas (`UserBase`/`UserCreate`/`UserRead` pattern: base fields shared, `*Create` adds write-only fields and validators, `*Read` adds `from_attributes=True` and server-generated fields).
- `app/core/config.py` — single `Config(BaseSettings)` loaded from `.env`, exported as a module-level `config` singleton; exposes computed `database_url` for SQLAlchemy. Add new env-driven settings here rather than reading `os.environ` directly.

## Database & migrations

- Postgres runs via `docker-compose.yml`, configured entirely from `.env` (see `.env.example` for required vars: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`).
- Alembic's `script_location` is `alembic/` and `prepend_sys_path = src`, so migration env code can `import app...`.
- When adding/changing a model in `app/db/models.py`, generate a migration with `make migration m="..."` (autogenerate diffs against `Base.metadata`), review the generated file, then apply with `make migrate`.

## Conventions

- Ruff config (`pyproject.toml`): line length 100, target py311, rule sets `E, F, I, N, UP, B, SIM`, `E501` ignored. `tests/*` ignores `ARG001` (unused args, e.g. fixtures).
- mypy uses the `pydantic.mypy` plugin so `pydantic-settings` fields populated from the environment type-check correctly.
