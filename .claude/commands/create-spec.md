---
description: Create a spec file and feature branch for the python fastapi app
argument-hint: "Step number and feature name e.g. 2 registration"
allowed-tools: Read, Write, Glob, Grep, Bash(git:*)
---

You are a senior developer spinning up a new feature for this FastAPI app.
Always follow the rules in `CLAUDE.md`.

Before writing the spec, ask the user for a brief explanation of the
feature and any clarification questions you need. Do not guess at scope —
a spec built on assumptions wastes the implementation pass.

User input: $ARGUMENTS

## Step 1 — Check working directory is clean
Run `git status`. If there are staged, unstaged, or untracked changes,
stop and tell the user to commit or stash first. DO NOT CONTINUE until
the working directory is clean.

Exception: `.claude/specs/` is this command's own output. Untracked files
there do not block.

## Step 2 — Parse the arguments
From $ARGUMENTS extract:

1. `step_number` — zero-padded to 2 digits: 2 → 02, 11 → 11
2. `feature_title` — human readable Title Case, e.g. "Registration",
   "Login and Logout", "Login JWT Generation"
3. `feature_slug` — lowercase kebab-case, only `a-z0-9-`, max 40 chars
4. `branch_name` — `feature/<feature_slug>`

If you cannot infer these, ask the user before proceeding.

## Step 3 — Check branch name is not taken
Run `git branch`. If `branch_name` exists, append a counter:
`feature/registration-01`, `feature/registration-02`, etc.

## Step 4 — Switch to main and pull latest
```
git checkout main
git pull origin main
```
If there is no `main` branch, no commits, or no `origin` remote, say so
and ask the user how to proceed rather than inventing a base.

## Step 5 — Create and switch to the feature branch
```
git checkout -b <branch_name>
```

## Step 6 — Research the codebase
This is a `src/` layout FastAPI app. `pythonpath = ["src"]` in
`pyproject.toml` and `--app-dir src` in the Makefile mean imports are
always `from app...`, never `from src.app...`.

Read before writing the spec:

- `CLAUDE.md` — commands, architecture, conventions. Authoritative.
- `src/app/main.py` — app instance, router registration (routers mount
  under the `/api/v1` prefix), raw `/health` and `/health/db` endpoints.
- `src/app/api/routes/` — `APIRouter` modules. `user_routes.py` is the
  reference pattern: `router = APIRouter(prefix=..., tags=[...])`, a
  local `get_<x>_service(db: DbSession)` factory, and an
  `Annotated[Service, Depends(factory)]` alias used by handlers.
- `src/app/services/` — business logic, one class per resource, takes a
  `Session` in `__init__`. Never calls `db.close()`.
- `src/app/schema/` — Pydantic v2 schemas. `UserBase`/`UserCreate`/
  `UserRead` pattern: base holds shared fields, `*Create` adds
  write-only fields plus `field_validator`s, `*Read` sets
  `from_attributes=True` and adds server-generated fields.
- `src/app/db/models.py` — SQLAlchemy ORM models using `Mapped[...]` /
  `mapped_column(...)`, inheriting `Base` and `TimestampMixin`. This is
  the source of truth for the schema — verify every claimed column here.
- `src/app/db/base.py` — declarative `Base` with the shared constraint
  naming convention (Alembic autogenerate depends on it) and
  `TimestampMixin` (`created_at` / `updated_at` server defaults).
- `src/app/db/deps.py` — `get_db()` yields a `Session` and closes it
  after the request; exposed as the `DbSession` annotated type.
- `src/app/db/session.py` — `engine` and `SessionLocal` built from
  `config.database_url`.
- `src/app/core/config.py` — single `Config(BaseSettings)` loaded from
  `.env`, exported as the module-level `config` singleton, with a
  computed `database_url`. New env-driven settings go here.
- `src/app/core/security.py` — bcrypt `hash_password` / `verify_password`.
- `alembic/versions/` — existing migrations. Check what is already
  applied before proposing schema changes.
- `tests/` — pytest + `TestClient`. Note `test_health_db` needs Postgres.
- `.claude/specs/*.md` — existing specs; avoid duplicating scope.

Confirm in `CLAUDE.md` and `.claude/specs/` that this step is not already
done. If it is, warn the user and stop.

## Step 7 — Write the spec
Use this exact structure. Omit no section; write "None" where empty.

---
# Spec: <feature_title>

## Overview
One paragraph: what the feature does, and why it belongs at this step.

## Depends on
Which previous steps must be complete. "None" if it stands alone.

## Routes
Every new or changed endpoint:
- `METHOD /api/v1/path` — description — request schema → response schema
  — status code — access level (public / authenticated)

If none: "No new routes".

## Schemas
Pydantic models to add or change, in `src/app/schema/`. Follow the
`*Base` / `*Create` / `*Read` split. Name the validators needed.

If none: "No schema changes".

## Database changes
New tables, columns, constraints, or indexes. Verify against
`src/app/db/models.py` and `alembic/versions/` first. State the
`make migration m="..."` message to use.

If none: "No database changes".

## Services
Service classes and methods to add or change in `src/app/services/`,
with signatures.

## Config
New settings for `Config` in `src/app/core/config.py`, and the matching
keys to document in `.env.example`.

If none: "No config changes".

## Files to change
Every file that will be modified, each with a one-line reason.

## Files to create
Every new file, each with a one-line purpose.

## New dependencies
New packages to add via `uv add`. Check `pyproject.toml` first — it
already includes fastapi, sqlalchemy, alembic, psycopg, pydantic[email],
pydantic-settings, pyjwt, bcrypt, structlog, uvicorn, gunicorn.

If none: "No new dependencies".

## Tests
Test files and cases to add under `tests/`, covering the success path
and each failure path. Note which require a live Postgres.

## Rules for implementation
Specific constraints. Always include:
- Imports are `from app...`, never `from src.app...`
- Request flow is routes → service → db model; no DB queries in route
  handlers, no `HTTPException` raised from `db/` modules
- Services take a `Session` in `__init__` and never call `db.close()` —
  the request-scoped `get_db` dependency owns the session lifecycle
- Routers depend on a local `get_<x>_service` factory exposed as an
  `Annotated[..., Depends(...)]` alias, mirroring `user_routes.py`
- SQLAlchemy 2.0 style: `Mapped[...]` / `mapped_column(...)`, inheriting
  `Base` (+ `TimestampMixin` where timestamps apply)
- Schema changes go through Alembic autogenerate (`make migration
  m="..."`), and the generated file is reviewed before `make migrate`
- Passwords are hashed with `app.core.security` (bcrypt) — never stored
  plaintext, never returned in a `*Read` schema
- New settings go in `Config` in `app/core/config.py`; never read
  `os.environ` directly. Secrets stay in `.env`, and `.env.example`
  documents every new key with a placeholder
- Ruff: line length 100, rules `E, F, I, N, UP, B, SIM`. Code must pass
  `make check` (lint + typecheck + test)
- Full type annotations on every new function and method — mypy runs
  over `src`

## Definition of done
A testable checklist. Each item verifiable by running a command
(`make check`, `make migrate`, `uv run pytest tests/test_x.py::test_y`)
or by hitting an endpoint and naming the expected status and body.
---

## Step 8 — Save the spec
Write to `.claude/specs/<step_number>-<feature_slug>.md`.

## Step 9 — Report to the user
Print exactly:
```
Branch:    <branch_name>
Spec file: .claude/specs/<step_number>-<feature_slug>.md
Title:     <feature_title>
```

Then say:
"Review the spec at `.claude/specs/<step_number>-<feature_slug>.md`
then enter Plan Mode with Shift+Tab twice to begin implementation."

Do not print the full spec in chat unless explicitly asked.
