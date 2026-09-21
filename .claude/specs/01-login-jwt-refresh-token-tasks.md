# Tasks: Login JWT And Refresh Token

Technical task breakdown for `01-login-jwt-refresh-token.md`. Ordered so
that each task compiles and type-checks against the ones before it.
Nothing here extends the spec's scope: no rate limiting, no password
reset, no email verification, no OAuth, no async conversion, no changes
to `GET /users/{user_id}` or `POST /users/`, and no edits to
`src/app/schema/user.py`, `src/app/db/base.py`, `src/app/db/deps.py`,
`src/app/db/session.py`, `src/app/main.py`, or `tests/test_smoke.py`.

Branch: `feature/login-jwt-refresh-token`. Migration head at start:
`e35634bf53ec`.

---

## Task 1 — Config settings

**File:** `src/app/core/config.py` (modify)

Add four fields to `Config`, after the existing `postgres_*` block and
before the `database_url` property:

```python
jwt_secret: str
jwt_algorithm: str = "HS256"
access_token_expire_minutes: int = 15
refresh_token_expire_days: int = 30
```

`jwt_secret` is annotated with no default, so a missing `JWT_SECRET`
raises `ValidationError` when the module-level `config = Config()` runs
at import.

Do not touch `model_config`, `app_name`, `app_version`, the `postgres_*`
fields, or `database_url`.

**Verify:** `uv run python -c "from app.core.config import config; print(config.jwt_algorithm)"`
with `src` on the path — or just let Task 10 cover it.

---

## Task 2 — `.env.example` keys

**File:** `.env.example` (modify)

Append a new block below the Postgres block:

```
# JWT auth (consumed by app.core.config)
JWT_SECRET=change-me-generate-with-openssl-rand-hex-32
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30
```

**Also add the same four keys to your local `.env`** with a real secret
(`openssl rand -hex 32`), or every subsequent task fails at import.
`.env` is gitignored; do not commit it.

---

## Task 3 — Token schemas

**File:** `src/app/schema/token.py` (create)

Three Pydantic v2 models. No `from_attributes` — none of these is built
from an ORM object.

- `TokenPair(BaseModel)`
  - `access_token: str`
  - `refresh_token: str`
  - `token_type: str = "bearer"`
  - `expires_in: int`
- `LoginResponse(TokenPair)`
  - `user: UserRead` — login only; `/refresh` returns a bare `TokenPair`
- `RefreshRequest(BaseModel)`
  - `refresh_token: str`
- `TokenPayload(BaseModel)`
  - `sub: str`
  - `exp: datetime`
  - `iat: datetime`
  - `jti: str`
  - `type: Literal["access", "refresh"]`

`TokenPayload` is the validation gate for decoded claims: constructing it
from a decoded dict raises `ValidationError` if `type` is anything other
than those two strings, or if a claim is missing. Import `Literal` from
`typing` and `datetime` from `datetime`.

---

## Task 4 — Security helpers

**File:** `src/app/core/security.py` (modify — append only)

Leave `hash_password` and `verify_password` exactly as they are. Add:

```python
def hash_token(token: str) -> str
```
Returns `hashlib.sha256(token.encode()).hexdigest()` — 64 hex chars,
matching the `String(64)` column. Used for both storing and looking up
refresh tokens, so an exact-match index lookup works.

```python
def create_token(subject: str, token_type: Literal["access", "refresh"], expires_delta: timedelta) -> tuple[str, str, datetime]
```
Builds the claim set and returns `(encoded_jwt, jti, expires_at)`:
- `sub = subject` (the user id, stringified — JWT `sub` must be a string)
- `iat = datetime.now(UTC)`
- `exp = iat + expires_delta`
- `jti = str(uuid.uuid4())`
- `type = token_type`

Encode with `jwt.encode(claims, config.jwt_secret, algorithm=config.jwt_algorithm)`.
Returning `jti` and `expires_at` spares the caller from decoding its own
freshly minted token to persist those values.

```python
def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> TokenPayload
```
- `jwt.decode(token, config.jwt_secret, algorithms=[config.jwt_algorithm])`
  — PyJWT verifies the signature and `exp` itself and raises
  `jwt.PyJWTError` (base class) on any failure.
- Wrap in `try/except jwt.PyJWTError` and re-raise as a module-local
  `TokenError` (a plain `Exception` subclass defined in this file).
- Validate the result through `TokenPayload(**claims)`, catching
  pydantic's `ValidationError` and raising `TokenError` too.
- If `payload.type != expected_type`, raise `TokenError`.

`TokenError` exists so this module raises no `HTTPException` — `core/` is
not the HTTP layer. The service layer translates it to a `401`.

**Scope note:** PyJWT 2.14 is already pinned in `pyproject.toml`;
`hashlib` and `uuid` are stdlib. No `uv add`.

---

## Task 5 — RefreshToken model

**File:** `src/app/db/models.py` (modify — append only)

Leave `User` untouched. Add below it:

```python
class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
```

New imports needed in this file: `datetime` from `datetime`, and
`DateTime` + `ForeignKey` from `sqlalchemy` (it currently imports only
`String` and `Uuid`). `created_at` / `updated_at` come from
`TimestampMixin`.

No `relationship()` in either direction — nothing in this spec needs to
traverse from a `User` to its tokens, and adding one would change `User`.

Add a `__repr__` mirroring `User`'s style, excluding `token_hash`.

---

## Task 6 — Migration

Run:
```
make db-up
make migration m="create refresh tokens table"
```

Then **review the generated file** in `alembic/versions/` before
applying. Confirm:
- `op.create_table("refresh_tokens", ...)` with all seven columns
  (five above + `created_at` + `updated_at`).
- The FK is named `fk_refresh_tokens_user_id_users` (from `base.py`'s
  `NAMING_CONVENTION`) and **carries `ondelete="CASCADE"`** — autogenerate
  sometimes omits it; add it by hand if missing.
- A unique index on `token_hash` and a plain index on `user_id`.
- `down_revision = "e35634bf53ec"`.
- `downgrade()` drops the indexes and the table.

Then `make migrate`.

Do not modify, squash, or delete the four existing revisions.

---

## Task 7 — AuthService

**File:** `src/app/services/auth_service.py` (create)

`class AuthService` with `def __init__(self, db: Session) -> None:
self.db = db` — same shape as `UserService`. No `db.close()` anywhere.

Define one module-level constant for the reused error:
```python
CREDENTIALS_ERROR = HTTPException(status_code=401, detail="Could not validate credentials")
```
Raising the same generic message for every token failure is what keeps
the endpoint from leaking whether a token was unknown, expired, or
revoked.

### `issue_pair(self, user: User) -> TokenPair`
1. `create_token(str(user.id), "access", timedelta(minutes=config.access_token_expire_minutes))`
2. `create_token(str(user.id), "refresh", timedelta(days=config.refresh_token_expire_days))`
3. Persist a `RefreshToken` row: `user_id=user.id`,
   `token_hash=hash_token(refresh_jwt)`, `expires_at` from the helper's
   third return value.
4. `self.db.add(...)`, `self.db.commit()`.
5. Return `TokenPair(access_token=..., refresh_token=...,
   expires_in=config.access_token_expire_minutes * 60)`.

### `refresh(self, refresh_token: str) -> TokenPair`
1. `decode_token(refresh_token, "refresh")` inside
   `try/except TokenError: raise CREDENTIALS_ERROR`. This rejects a
   forged signature, an expired `exp`, and an access token presented here.
2. Look up the row by `hash_token(refresh_token)`. Missing → `401`.
   (A signature-valid token with no row means it was never issued by
   this deployment, or the row was deleted.)
3. `row.revoked_at is not None` → `401`.
4. `row.expires_at <= datetime.now(UTC)` → `401`. Redundant with the JWT
   `exp` check, but the DB is the authority on revocation state and the
   two must agree.
5. Load the `User` by `payload.sub`. Missing → `401` (user deleted since
   issuance).
6. Set `row.revoked_at = datetime.now(UTC)` — **rotation**: the presented
   token is spent.
7. `return self.issue_pair(user)` — which commits both the revocation
   and the new row in its own `commit()`.

### `revoke(self, refresh_token: str) -> None`
Look up by `hash_token(refresh_token)`. If found and not already revoked,
set `revoked_at` and commit. If not found or already revoked, return
normally — **no exception**, so `POST /logout` is idempotent and cannot
be used to probe which tokens exist. Do not decode the JWT here; a
malformed string simply hashes to nothing on record.

### `get_user_from_access_token(self, token: str) -> User`
1. `decode_token(token, "access")`, `TokenError` → `401`. The
   `expected_type` argument is what rejects a refresh token used as a
   bearer.
2. `uuid.UUID(payload.sub)` inside `try/except ValueError: raise
   CREDENTIALS_ERROR` — `sub` is attacker-influenced only via a valid
   signature, but a non-UUID string would otherwise raise a 500 from
   `db.get`.
3. `self.db.get(User, user_id)`; `None` → `401`.
4. Return the `User`.

Use `self.db.query(RefreshToken).filter(...).first()`, matching the style
already in `UserService.login`.

---

## Task 8 — Auth dependency

**File:** `src/app/api/deps.py` (create)

```python
bearer_scheme = HTTPBearer(auto_error=False)
```
`auto_error=False` is deliberate: the default raises a `403` on a missing
header, and the spec requires `401`.

```python
def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
```
- `credentials is None` → raise `401` with the same generic detail.
- Otherwise `return AuthService(db).get_user_from_access_token(credentials.credentials)`.

```python
CurrentUser = Annotated[User, Depends(get_current_user)]
```

Include `WWW-Authenticate: Bearer` in the `headers` of the 401s raised
here, per RFC 6750.

Imports: `HTTPBearer` / `HTTPAuthorizationCredentials` from
`fastapi.security`, `DbSession` from `app.db.deps`, `User` from
`app.db.models`, `AuthService` from `app.services.auth_service`.

---

## Task 9 — UserService.login + routes

**File:** `src/app/services/user_service.py` (modify)

Change `login` only:
```python
def login(self, data: UserLoginRequest) -> LoginResponse:
    user = self.db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return AuthService(self.db).issue_pair(user)
```
The credential check is unchanged — only the return value differs.
`AuthService` is constructed with the same `Session`, so both services
share one transaction. Leave `get` and `create` alone.

**File:** `src/app/api/routes/user_routes.py` (modify)

Keep `get_user_service`, `UserServiceDep`, `get_user`, and `create_user`
untouched. Add an `AuthService` factory mirroring the existing pattern:

```python
def get_auth_service(db: DbSession) -> AuthService:
    return AuthService(db)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
```

Then:
- `login_user` — change `response_model=UserRead` to
  `response_model=LoginResponse`. Body unchanged.
- `POST /refresh`, `status_code=200`, `response_model=TokenPair` —
  `def refresh_token(data: RefreshRequest, service: AuthServiceDep)`,
  returns `service.refresh(data.refresh_token)`.
- `POST /logout`, `status_code=204`, `response_class=Response` —
  calls `service.revoke(data.refresh_token)` and returns `None`. A 204
  must have an empty body, so set no `response_model`.
- `GET /me`, `status_code=200`, `response_model=UserRead` —
  `def read_me(user: CurrentUser)`, returns `user`. No service needed.

**Route ordering matters:** declare `/me` **before** the existing
`GET /{user_id}`. FastAPI matches in declaration order, so a `/me`
declared after `/{user_id}` would be swallowed by it and try to parse
`"me"` as a user id.

`main.py` needs no change — the router is already mounted at `/api/v1`
and all four routes live on it.

---

## Task 10 — Tests

**File:** `tests/test_auth.py` (create)

`TestClient(app)` as in `test_smoke.py`. All cases need Postgres up and
migrated. Add a module docstring saying so.

Helper: a function creating a unique user per test —
`f"jwt-{uuid.uuid4()}@example.com"` with a password satisfying
`UserCreate.validate_password_strength` (upper + digit + special, ≥6),
e.g. `"Passw0rd!"` — then logging in and returning the `LoginResponse` body.
Unique emails matter because `users.email` is uniquely indexed and these
tests commit real rows.

Success cases:
1. `test_login_returns_token_pair` — both tokens present,
   `token_type == "bearer"`, `expires_in > 0`.
2. `test_me_returns_current_user` — `200`, `email` matches, and
   `"password" not in resp.json()`.
3. `test_refresh_rotates_tokens` — `200`, and both returned tokens
   differ from those sent.
4. `test_logout_returns_204` — `204` and empty body.

Failure cases:
5. `test_login_wrong_password` → `401`.
6. `test_me_without_header` → `401`.
7. `test_me_with_garbage_token` → `401`.
8. `test_me_rejects_refresh_token` → `401` (guards the `type` claim).
9. `test_refresh_token_is_single_use` — refresh twice with the same
   token; second → `401` (guards rotation).
10. `test_refresh_after_logout` → `401` (guards revocation).
11. `test_me_with_expired_token` → `401`. Build it with
    `create_token(str(uuid.uuid4()), "access", timedelta(minutes=-5))`
    — a negative delta yields a past `exp`. Do not `sleep`.

Note on 3 and 9: `iat`/`exp` have 1-second JWT resolution, but `jti` is a
fresh UUID per call, so rotated tokens always differ even when minted
within the same second.

---

## Task 11 — Verification

```
make format
make check
```

Then the manual pass from the spec's Definition of Done. With the app
running (`make dev`):

```
# create
curl -s -XPOST localhost:8000/api/v1/users/ -H 'content-type: application/json' \
  -d '{"name":"Ada","email":"ada@example.com","password":"Passw0rd!"}'
# login -> capture tokens
curl -s -XPOST localhost:8000/api/v1/users/login -H 'content-type: application/json' \
  -d '{"email":"ada@example.com","password":"Passw0rd!"}'
# me
curl -s localhost:8000/api/v1/users/me -H "authorization: Bearer $ACCESS"
# refresh, then replay the same token (expect 401 the second time)
curl -s -XPOST localhost:8000/api/v1/users/refresh -H 'content-type: application/json' \
  -d "{\"refresh_token\":\"$REFRESH\"}"
# logout
curl -s -o /dev/null -w '%{http_code}\n' -XPOST localhost:8000/api/v1/users/logout \
  -H 'content-type: application/json' -d "{\"refresh_token\":\"$REFRESH2\"}"
```

Also confirm:
- `make db-shell` → `\d refresh_tokens` shows the unique index on
  `token_hash` and the CASCADE FK.
- `select token_hash from refresh_tokens;` → only 64-char hex, no JWTs
  (no `eyJ...` prefixes).
- `make downgrade` drops the table cleanly, then `make migrate` again.
- Unsetting `JWT_SECRET` in `.env` makes the app fail at startup with a
  pydantic `ValidationError`.
- `/docs` lists `login`, `refresh`, `logout`, `me`, with the bearer
  padlock on `me`.

---

## Dependency order

```
1 Config ─┬─> 4 Security ─┬─> 7 AuthService ─┬─> 8 deps ──> 9 routes ──> 10 tests ──> 11 verify
2 .env ───┘   3 Schemas ──┘                  │
              5 Model ──> 6 Migration ───────┘
```

Tasks 1–5 are independent edits and can be done in any order. Task 6
needs 5. Task 7 needs 3, 4, 5. Task 9 needs 7 and 8. Task 10 needs
everything, plus a migrated database.

## Out of scope — do not add

Password reset, email verification, rate limiting or lockout on failed
logins, token denylist for *access* tokens (they expire in 15 minutes by
design), `OAuth2PasswordBearer` / form-encoded login, refresh-token reuse
*detection* (revoking a whole family on replay), a `relationship()` on
`User`, async/await conversion, a `/users` list route, pagination, or
role/permission fields. Each is a defensible next step; none is in this
spec.
