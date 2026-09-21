import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt
from pydantic import ValidationError

from app.core.config import config
from app.schema.token import TokenPayload


class TokenError(Exception):
    """A token could not be decoded, or carried the wrong type.

    Deliberately not an HTTPException: `core/` is not the HTTP layer, so
    the service layer translates this into a 401.
    """


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # stored value isn't a valid bcrypt hash (e.g. a pre-hashing row)
        return False


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token, for storage and exact-match lookup.

    Not bcrypt: a JWT is already high-entropy random data, so it needs no
    slow KDF, and lookup has to be an indexed equality match. 64 chars,
    matching the String(64) column.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(
    subject: str,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta,
) -> tuple[str, str, datetime]:
    """Mint a JWT. Returns (encoded, jti, expires_at).

    Returning jti and expires_at spares the caller from decoding a token
    it just created in order to persist those values.
    """
    issued_at = datetime.now(UTC)
    expires_at = issued_at + expires_delta
    jti = str(uuid.uuid4())

    claims = {
        "sub": subject,
        "iat": issued_at,
        "exp": expires_at,
        "jti": jti,
        "type": token_type,
    }
    encoded = jwt.encode(claims, config.jwt_secret, algorithm=config.jwt_algorithm)
    return encoded, jti, expires_at


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> TokenPayload:
    """Decode and validate a JWT, or raise TokenError.

    PyJWT verifies the signature and `exp` itself. `expected_type` is what
    keeps access and refresh tokens from being interchangeable.
    """
    try:
        claims = jwt.decode(token, config.jwt_secret, algorithms=[config.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError("could not decode token") from exc

    try:
        payload = TokenPayload(**claims)
    except ValidationError as exc:
        raise TokenError("token claims failed validation") from exc

    if payload.type != expected_type:
        raise TokenError(f"expected a {expected_type} token")

    return payload
