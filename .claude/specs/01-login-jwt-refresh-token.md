# Spec: Login JWT And Refresh Token

## Overview
Turns the existing `POST /api/v1/users/login` endpoint — which today
verifies a bcrypt password and returns a bare `UserRead` body with no
credential — into real token-based authentication. Login issues a
short-lived access token plus a long-lived refresh token; the refresh
token is persisted so it can be revoked; a `get_current_user` dependency
decodes the bearer access token and loads the `User`, making protected
routes possible; and logout revokes the stored refresh token. This is the
first step because every subsequent resource route needs a way to answer
"who is calling?", and there is currently no such mechanism.

## Depends on
None as a numbered step, but it builds on code already committed at
`e3ca6b7`: the `User` model, `app.core.security` (bcrypt
`hash_password` / `verify_password`), `UserService.login`, and the
`UserLoginRequest` schema. Those exist and are working; this spec
replaces `login`'s return value and adds to it.

## Routes
All under the existing `users` router (`prefix="/users"`, mounted at
`/api/v1` by `main.py`), except the auth-specific ones noted below.

- `POST /api/v1/users/login` — **changed.** Verifies credentials and
  issues tokens. `UserLoginRequest` → `TokenPair`. `200`. Public.
  Currently returns `UserRead`; that is a breaking response change.
- `POST /api/v1/users/refresh` — exchanges a valid, unrevoked,
  unexpired refresh token for a new access token (and a rotated refresh
  token). `RefreshRequest` → `TokenPair`. `200`. Public (the refresh
  token itself is the credential).
- `POST /api/v1/users/logout` — revokes the supplied refresh token.
  `RefreshRequest` → `204 No Content`. Public (idempotent: revoking an
  already-revoked or unknown token still returns `204`, so the endpoint
  cannot be used to probe which tokens exist).
- `GET /api/v1/users/me` — returns the authenticated caller.
  No body → `UserRead`. `200`. Authenticated.

Failure responses to implement explicitly:
- `401` invalid credentials on login (already the case).
- `401` missing, malformed, expired, or wrong-type access token on a
  protected route.
- `401` unknown, expired, revoked, or wrong-type refresh token on refresh.

## Schemas
In `src/app/schema/token.py` (new file — these are not `User` shapes):

- `TokenPair(BaseModel)` — `access_token: str`, `refresh_token: str`,
  `token_type: str = "bearer"`, `expires_in: int` (access token lifetime
  in seconds, so clients need not decode the JWT).
- `RefreshRequest(BaseModel)` — `refresh_token: str`.
- `TokenPayload(BaseModel)` — decoded claim set for internal validation:
  `sub: str` (the user id as a string), `exp: datetime`,
  `iat: datetime`, `jti: str`, `type: Literal["access", "refresh"]`.

No `*Base` / `*Create` / `*Read` split applies here — these are
transport shapes, not a persisted resource being created and read. The
`type` claim is what stops a refresh token being replayed as an access
token; `TokenPayload` validating it as a `Literal` is the enforcement
point.

`src/app/schema/user.py` is unchanged. `UserRead` already omits
`password`, which is what `GET /users/me` needs.

## Database changes
One new table. Verified against `src/app/db/models.py` (only `User`
exists) and `alembic/versions/` (head is `e35634bf53ec`; the chain is
`96e5be06af94` → `25d12fb63ced` → `c3628dc864f7` → `e35634bf53ec`, and
the last two are empty no-op revisions).

`RefreshToken(Base, TimestampMixin)`, `__tablename__ = "refresh_tokens"`:

| column | type | notes |
| --- | --- | --- |
| `id` | `Uuid` | primary key, `default=uuid.uuid4` |
| `user_id` | `Uuid` | `ForeignKey("users.id", ondelete="CASCADE")`, indexed |
| `token_hash` | `String(64)` | SHA-256 hex of the token, unique, indexed |
| `expires_at` | `DateTime(timezone=True)` | absolute expiry |
| `revoked_at` | `DateTime(timezone=True)` | nullable; non-null means revoked |

`created_at` / `updated_at` come from `TimestampMixin`.

Store only a **hash** of the refresh token, never the token itself — a
leaked database dump must not yield usable credentials. SHA-256 is
correct here rather than bcrypt: the token is high-entropy random data,
so it needs no slow KDF, and lookup must be an indexed exact match.

Generate with:
```
make migration m="create refresh tokens table"
```
Review the generated file (confirm the FK is named
`fk_refresh_tokens_user_id_users` per the `base.py` naming convention,
and that `ondelete="CASCADE"` survived autogenerate — Alembic sometimes
drops it), then `make migrate`.

## Services
`src/app/services/user_service.py` — change:
- `login(self, data: UserLoginRequest) -> TokenPair` — was
  `-> User`. Verifies as today, then delegates to `AuthService` for
  issuance.

`src/app/services/auth_service.py` (new) — `AuthService`, taking
`db: Session` in `__init__` like every other service:
- `issue_pair(self, user: User) -> TokenPair` — mints both tokens,
  persists the refresh token's hash.
- `refresh(self, refresh_token: str) -> TokenPair` — validates, revokes
  the presented token, issues a replacement pair (rotation).
- `revoke(self, refresh_token: str) -> None` — sets `revoked_at`.
  Silent when the token is unknown.
- `get_user_from_access_token(self, token: str) -> User` — decodes,
  checks `type == "access"`, loads the `User`, raises `401` if absent.

Rotation on refresh is deliberate: a refresh token is single-use, so a
stolen one is only usable until the legitimate client next refreshes.

## Config
New settings on `Config` in `src/app/core/config.py`:

- `jwt_secret: str` — **no default.** A default would ship a signing key
  that forges tokens in any deployment that forgot to set it; absent it,
  `Config()` fails loudly at import.
- `jwt_algorithm: str = "HS256"`
- `access_token_expire_minutes: int = 15`
- `refresh_token_expire_days: int = 30`

Matching `.env.example` keys, with placeholders:
```
JWT_SECRET=change-me-generate-with-openssl-rand-hex-32
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30
```

## Files to change
- `src/app/core/config.py` — add the four JWT settings.
- `src/app/core/security.py` — add JWT encode/decode and token-hashing
  helpers alongside the existing bcrypt functions.
- `src/app/db/models.py` — add the `RefreshToken` model.
- `src/app/schema/user.py` — no change; listed only to record that it
  was checked and `UserRead` already excludes `password`.
- `src/app/services/user_service.py` — `login` returns `TokenPair`.
- `src/app/api/routes/user_routes.py` — change `login`'s
  `response_model`; add `refresh`, `logout`, `me`.
- `.env.example` — document the four new keys.

## Files to create
- `src/app/schema/token.py` — `TokenPair`, `RefreshRequest`, `TokenPayload`.
- `src/app/services/auth_service.py` — `AuthService`.
- `src/app/api/deps.py` — `get_current_user` dependency and the
  `CurrentUser` annotated alias, using FastAPI's `HTTPBearer`.
  Lives beside the routes it serves, mirroring how `db/deps.py` sits
  beside the db layer.
- `alembic/versions/<hash>_create_refresh_tokens_table.py` — generated,
  not hand-written.
- `tests/test_auth.py` — see below.

## New dependencies
No new dependencies. `pyproject.toml` already pins `pyjwt>=2.14.0` and
`bcrypt>=5.0.0`; `hashlib` for the SHA-256 token hash is stdlib.

## Tests
`tests/test_auth.py`, using `TestClient` as `test_smoke.py` does. All of
these hit the database, so **all require a live Postgres** (`make db-up`)
and a migrated schema (`make migrate`).

Success paths:
- Register then login → `200`, body has `access_token`, `refresh_token`,
  `token_type == "bearer"`, and a positive `expires_in`.
- `GET /users/me` with the access token → `200`, correct `email`, and
  **no `password` key in the body**.
- `POST /users/refresh` with a fresh refresh token → `200`, and the
  returned tokens differ from the originals (proves rotation).
- `POST /users/logout` → `204`.

Failure paths:
- Login with a wrong password → `401`.
- `GET /users/me` with no `Authorization` header → `401`.
- `GET /users/me` with a malformed/garbage token → `401`.
- `GET /users/me` presenting a **refresh** token as the bearer → `401`
  (guards the `type` claim).
- `POST /users/refresh` reusing a refresh token already spent by a prior
  refresh → `401` (guards rotation).
- `POST /users/refresh` after logout → `401` (guards revocation).
- `GET /users/me` with an expired access token → `401`. Construct it by
  signing a token with a past `exp` rather than by sleeping.

## Rules for implementation
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

Feature-specific:
- Never store a raw refresh token — persist `sha256(token)` only
- Every JWT carries a `type` claim (`"access"` or `"refresh"`) and the
  decode path asserts the expected value; an access token and a refresh
  token are never interchangeable
- Use timezone-aware UTC datetimes throughout (`datetime.now(UTC)`), to
  match the `DateTime(timezone=True)` columns
- Auth failures return `401` with a generic `"Invalid credentials"` or
  `"Could not validate credentials"` detail — never reveal whether the
  email existed, or whether a token was unknown vs. expired vs. revoked
- `jwt_secret` has no default value in `Config`
- Refresh is single-use: rotate and revoke the presented token

## Definition of done
- [ ] `make check` passes (ruff, mypy over `src`, pytest).
- [ ] `make migration m="create refresh tokens table"` produced a
      reviewed migration, and `make migrate` applies cleanly from the
      current head `e35634bf53ec`.
- [ ] `make downgrade` cleanly drops `refresh_tokens`.
- [ ] `make db-shell` → `\d refresh_tokens` shows the unique index on
      `token_hash` and the FK to `users` named per `base.py`'s convention.
- [ ] `uv run pytest tests/test_auth.py` passes with Postgres up.
- [ ] `POST /api/v1/users/` creates a user → `201`.
- [ ] `POST /api/v1/users/login` with that user → `200` carrying both
      tokens; with a wrong password → `401`.
- [ ] `GET /api/v1/users/me` with the access token → `200` and no
      `password` field; with no header → `401`; with the refresh token as
      bearer → `401`.
- [ ] `POST /api/v1/users/refresh` → `200` with different tokens than
      were sent; replaying that same refresh token → `401`.
- [ ] `POST /api/v1/users/logout` → `204`, and a subsequent refresh with
      that token → `401`.
- [ ] `make db-shell` → `select token_hash from refresh_tokens;` shows
      only 64-char hex digests, no JWTs.
- [ ] Starting the app with `JWT_SECRET` unset fails immediately with a
      pydantic validation error rather than booting.
- [ ] `/docs` lists `login`, `refresh`, `logout`, and `me`, with the
      bearer scheme shown on `me`.
